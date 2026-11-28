"""Stage the pinned Windows x64 plugin interpreters at build time (no system PATH lookup)."""
import argparse
import hashlib
from pathlib import Path
import shutil
import tempfile
import urllib.request
import zipfile


PYTHON = ("https://www.python.org/ftp/python/3.14.10/python-3.14.10-embed-amd64.zip",
          "90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159")
NODE = ("https://nodejs.org/dist/v24.22.3/node-v24.22.3-win-x64.zip",
        "e612af99f626ab415ea225af6bce5c971feb448cb5cae250bb1c3fa50c5f7d9f")


def archive(cache, url, digest):
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / url.rsplit("/", 1)[1]
    if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == digest:
        return target
    with tempfile.TemporaryDirectory(dir=cache) as stage:
        path = Path(stage) / "download"
        with urllib.request.urlopen(url, timeout=90) as response, path.open("wb") as out:
            shutil.copyfileobj(response, out)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Unexpected release checksum for {target.name}")
        path.replace(target)
    return target


def prepare(dest, cache):
    # Python's default ._pth restricts imports to the embedded standard library.
    for name, release in (("python", PYTHON), ("node", NODE)):
        target = dest / name
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive(cache, *release)) as z:
            if name == "python":
                z.extractall(target)
            else:
                for leaf in ("node.exe", "LICENSE"):
                    with z.open("node-v24.22.3-win-x64/" + leaf) as src, (target / leaf).open("wb") as out:
                        shutil.copyfileobj(src, out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.destination, args.cache)
