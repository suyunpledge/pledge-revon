"""Run with Revon.exe <this-script.py> <new-output-dir> [--reference <old-output-dir>]."""
import argparse
import json
import os
from pathlib import Path
import sys
from time import perf_counter_ns
from unittest.mock import patch

from PySide6.QtGui import QImage
from revon import model3d
from revon.policy import Mode, Policy, Sandbox
from revon.tools import ToolContext, build_builtin_registry


MODELS = {
    "box": {"op": "box", "size": [40, 30, 10]},
    "sphere": {"op": "sphere", "r": 10, "segments": 32},
    "plate": {"op": "difference", "children": [
        {"op": "box", "size": [40, 40, 10]},
        {"op": "cylinder", "d": 20, "h": 12, "translate": [20, 20, -1]}]},
    "torus": {"op": "torus", "major": 20, "minor": 5, "segments": 64, "tube_segments": 24},
}


def image(path):
    decoded = QImage(str(path)).convertToFormat(QImage.Format.Format_RGB888)
    if decoded.isNull() or (decoded.width(), decoded.height()) != (515, 515):
        raise ValueError(f"Invalid four-view preview: {path}")
    return decoded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--reference-only", action="store_true", help="record a single run with the old EXE")
    args = parser.parse_args()
    workspace = args.output.resolve()
    workspace.mkdir(parents=True, exist_ok=False)
    registry = build_builtin_registry()
    ctx = ToolContext(Policy(mode=Mode.ACCEPT_EDITS, sandbox=Sandbox.WORKSPACE_WRITE,
                             workspace=workspace, non_interactive=True), workspace)
    render = model3d.contact_sheet
    rows = []
    for trial in range(1 if args.reference_only else 3):
        order = ("python", "native") if trial % 2 == 0 else ("native", "python")
        for name, spec in MODELS.items():
            first = None
            for backend in (("reference",) if args.reference_only else order):
                elapsed = []

                def timed(mesh, size):
                    start = perf_counter_ns()
                    png = render(mesh, size)
                    elapsed.append((perf_counter_ns() - start) / 1e6)
                    return png

                rel = Path(str(trial + 1), backend, name + ".stl")
                selected = "python" if args.reference_only else backend
                with patch.dict(os.environ, REVON_3D_RENDERER=selected), patch.object(model3d, "contact_sheet", timed):
                    result = registry.invoke("model3d_build", {"spec": spec, "path": rel.as_posix()}, ctx)
                if not result.ok or len(elapsed) != 1:
                    raise RuntimeError(f"{rel}: {result.error} ({len(elapsed)} previews)")
                pixels = image((workspace / rel).with_suffix(".preview.png"))
                if first is not None and pixels != first:
                    raise ValueError(f"Python and C++ pixels differ: {rel}")
                if args.reference:
                    old = image(args.reference / "1" / "reference" / (name + ".preview.png"))
                    if pixels != old:
                        raise ValueError(f"Pixels differ from previous release: {rel}")
                first = pixels
                rows.append(dict(trial=trial + 1, model=name, backend=backend, ms=round(elapsed[0], 3)))
    report = {"exe": sys.executable, "module": model3d.__file__, "runs": rows}
    (workspace / "timings.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
