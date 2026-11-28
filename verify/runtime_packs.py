"""Revon.exe runtime_packs.py <new QA directory> [--clean]. Runs the desktop's real market and tool dispatcher."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import traceback


def verify(root, clean):
    from pack_runtime import PACKS, interpreter, location, runtime_dir
    from plugin_market import Marketplace
    from qt_frontend import plugin_page
    from qt_frontend.pack_tools import with_packs
    from revon.model3d import contact_sheet, native_preview
    from revon.model3d.mesh import torus

    host_tools = {name: shutil.which(name) for name in ("python", "python3", "node", "npm", "cl", "clang", "g++")}
    if clean and any(host_tools.values()):
        raise AssertionError(f"Unexpected system tool: {host_tools}")
    home, workspace = root / "home", root / "workspace"
    workspace.mkdir()
    market = Marketplace(home)
    connection = ({}, lambda *args: (_ for _ in ()).throw(AssertionError("unexpected route")))
    assert not with_packs(connection, home, workspace)[0]
    report = {"exe": sys.executable, "host_tools": host_tools, "packs": {}}
    for pid, pack in PACKS.items():
        row = next(r for r in plugin_page.view(home, market, workspace)["rows"] if r["id"] == pid)
        assert row["actions"][0]["key"] == "activatePack"
        plugin_page.act(home, market, workspace, "activatePack", {"id": pid}, lambda *_: True)
        env = location(home, pid)
        stamp = env.stat().st_mtime_ns
        plugin_page.act(home, market, workspace, "activatePack", {"id": pid}, lambda *_: True)
        assert env.stat().st_mtime_ns == stamp
        tools, dispatch = with_packs(connection, home, workspace)
        name = "keystone_" + pack["tool"]
        assert name not in with_packs(connection, home, root / "other-workspace")[0]
        text = ("The fox walked through the forest and watched the birds singing high in the trees."
                if pack["runtime"] == "python" else "# Alpha\n```ts\n# ignored\n```\n## Alpha")
        response = dispatch(tools[name][1], {"text": text}, threading.Event())
        assert response["ok"], response
        data = json.loads(response["content"])
        if pack["runtime"] == "python":
            assert data["language"] == "en" and data["candidates"][0]["probability"] > .9
        else:
            assert [(h["line"], h["anchor"]) for h in data["headings"]] == [(1, "alpha"), (5, "alpha-1")]
        market.revoke_grants(pid, workspace=workspace)
        assert not dispatch(tools[name][1], {"text": text}, threading.Event())["ok"]
        exe = interpreter(pack)
        assert exe.parent.parent == runtime_dir()
        report["packs"][pid] = {"runtime": str(exe), "version": subprocess.check_output([exe, "--version"]).decode().strip(),
                                "environment": str(env), "result": data, "reused": True, "revoked": True}
    mesh = torus(20, 5, 64, 24)
    png = contact_sheet(mesh, backend="native")
    assert native_preview.load() is not None and png == contact_sheet(mesh, backend="python")
    (root / "torus.png").write_bytes(png)
    report["native_preview"] = {"bytes": len(png), "matches_python": True}
    return report


if __name__ == "__main__":
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=False)
    try:
        data = verify(output, "--clean" in sys.argv[2:])
    except Exception:
        (output / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise SystemExit(1)
    (output / "results.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
