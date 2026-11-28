"""Install and run the desktop's curated, text-only compute packs."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

from plugin_market import linked, market_lock


ENTRIES = Path(__file__).resolve().with_name("pack_entries")
PACKS = {
    "pack-language-id": {
        "tool": "language_detect", "runtime": "python", "entry": "language_id.py",
        "tree": "776b23eeeb4fe40a4f98da78fc1e69713885f0978e142cce620ae05cc73eeafd",
        "libraries": [
            ("https://files.pythonhosted.org/packages/33/85/98532c24110055b5f7601e1bae17e894c5205f9c22e4845346e232a7f121/langdetect_py-1.1.1-py3-none-any.whl",
             "f31023136acc964992b9257d83af04f13116b89f026139d52da3567e462e38ee", "site"),
            ("https://files.pythonhosted.org/packages/b7/ce/149a00dd41f10bc29e5921b496af8b574d8413afcd5e30dfa0ed46c2cc5e/six-1.17.0-py2.py3-none-any.whl",
             "4721f391ed90541fddacab5acf947aa0d3dc7d27b2e1e8eda2be8970586c3274", "site"),
        ],
    },
    "pack-markdown-outline": {
        "tool": "markdown_outline", "runtime": "node", "entry": "markdown_outline.mts",
        "tree": "16e3da1110ae3bfb56b98b3217803557774b1f5663b1fdc3cd9564d5771dd032",
        "libraries": [
            ("https://registry.npmjs.org/github-slugger/-/github-slugger-2.0.0.tgz",
             "ddde66e96b7d722ff2c3d478e7595aeccae7e75dde798d405510d862f1367d0f", "node_modules/github-slugger"),
        ],
    },
}
TOOLS = {p["tool"]: pid for pid, p in PACKS.items()}
MAX_TEXT = 32768


def runtime_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "runtimes"
    return ENTRIES.parent / "desktop/build-source/pack-runtimes"


def interpreter(pack):
    name = pack["runtime"]
    path = runtime_dir() / name / (name + ".exe")
    if not path.is_file():
        raise ValueError(f"缺少随程序交付的 {name} 运行时，请安装新版 Windows x64 桌面包。")
    return path


def tree_digest(root):
    files = {}
    if linked(root):
        raise ValueError("能力包目录不能是链接。")
    for path in root.rglob("*"):
        if linked(path):
            raise ValueError("能力包内不支持链接。")
        if path.is_dir():
            continue
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 8 << 20:
            raise ValueError("能力包文件无效。")
        files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    listing = "".join(k + "\0" + files[k] + "\n" for k in sorted(files))
    return hashlib.sha256(listing.encode()).hexdigest()


def _dependency(url, checksum, offline):
    local = offline / url.rsplit("/", 1)[1]
    with (local.open("rb") if local.is_file() else urllib.request.urlopen(url, timeout=30)) as source:
        data = source.read((8 << 20) + 1)
    if len(data) > 8 << 20 or hashlib.sha256(data).hexdigest() != checksum:
        raise ValueError(f"依赖包校验失败：{local.name}")
    return io.BytesIO(data)


def _write_file(root, name, content):
    target = root / name
    if not target.resolve().is_relative_to(root.resolve()) or "\\" in name or ":" in name:
        raise ValueError("依赖包文件路径无效。")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as out:
        shutil.copyfileobj(content, out)


def location(home, pid):
    parent = Path(home) / "pack-environments" / pid
    if linked(parent) or linked(parent.parent):
        raise ValueError("能力包环境不能是链接。")
    return parent / PACKS[pid]["tree"]


def install(home, pid):
    pack = PACKS[pid]
    interpreter(pack)
    dest = location(home, pid)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with market_lock(dest.parent / "install.lock", timeout=90):
        if dest.exists() and tree_digest(dest) == pack["tree"]:
            return
        with tempfile.TemporaryDirectory(dir=dest.parent) as staging:
            root = Path(staging) / "new"
            root.mkdir()
            for url, digest, subdir in pack["libraries"]:
                data = _dependency(url, digest, runtime_dir().parent / "offline-packs")
                if url.endswith(".whl"):
                    with zipfile.ZipFile(data) as archive:
                        for info in archive.infolist():
                            if not info.is_dir():
                                with archive.open(info) as content:
                                    _write_file(root / subdir, info.filename, content)
                else:
                    with tarfile.open(fileobj=data, mode="r:gz") as archive:
                        for member in archive:
                            if member.isdir():
                                continue
                            if not member.isfile() or not member.name.startswith("package/"):
                                raise ValueError("npm 依赖包格式无效。")
                            with archive.extractfile(member) as content:
                                _write_file(root / subdir, member.name[len("package/"):], content)
            if tree_digest(root) != pack["tree"]:
                raise ValueError("解包后的依赖与锁定版本不符。")
            previous = Path(staging) / "previous"
            if dest.exists():
                dest.rename(previous)
            try:
                root.rename(dest)
            except OSError:
                if previous.exists():
                    previous.rename(dest)
                raise


def run(home, pid, args):
    if set(args) != {"text"} or not isinstance(args["text"], str) or not 0 < len(args["text"]) <= MAX_TEXT:
        raise ValueError(f"请提供 1 至 {MAX_TEXT} 个字符的 text。")
    pack = PACKS[pid]
    exe = interpreter(pack)
    deps = location(home, pid)
    if not deps.is_dir() or tree_digest(deps) != pack["tree"]:
        raise ValueError("能力包依赖缺失或已更改，请在插件市场重新安装。")
    entry = ENTRIES / pack["entry"]
    command = ([exe, "-I", "-S", "-B", "-X", "utf8", entry, deps / "site"] if pack["runtime"] == "python"
               else [exe, "--no-global-search-paths", entry, deps / "node_modules/github-slugger/index.js"])
    env = {k: v for k, v in os.environ.items() if k.upper() in {"WINDIR", "SYSTEMROOT", "TEMP", "TMP"}}
    result = subprocess.run(command, input=json.dumps(args).encode(), capture_output=True,
                            timeout=20, env=env, cwd=deps, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise RuntimeError(f"能力包 {pid} 执行失败（退出码 {result.returncode}）。")
    return json.loads(result.stdout)
