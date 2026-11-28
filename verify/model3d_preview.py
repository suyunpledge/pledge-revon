"""Run with Revon.exe <this-script.py> <new-output-dir> [--reference <old-output-dir>]."""
import argparse
from contextlib import ExitStack
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
    "torus_dense": {"op": "torus", "major": 20, "minor": 5, "segments": 192, "tube_segments": 64},
}


def image(path):
    decoded = QImage(str(path)).convertToFormat(QImage.Format.Format_RGB888)
    if decoded.isNull() or (decoded.width(), decoded.height()) != (515, 515):
        raise ValueError(f"Invalid four-view preview: {path}")
    return decoded


def profile_native(mesh, size):
    """Time whole batches at the ABI boundary, outside the uninstrumented tool runs."""
    from revon.model3d import native_preview as native, render

    ns = dict(projection=0, packing=0, raster=0, png=0)

    def timed(stage, func):
        def call(*args):
            start = perf_counter_ns()
            result = func(*args)
            ns[stage] += perf_counter_ns() - start
            return result
        return call

    api = native.load()
    with ExitStack() as hooks:
        hooks.enter_context(patch.object(render, "png_bytes", timed("png", render.png_bytes)))
        if hasattr(api, "project"):
            hooked = api._replace(project=timed("projection", api.project), raster=timed("raster", api.raster))
            hooks.enter_context(patch.object(native, "load", lambda: hooked))
            hooks.enter_context(patch.object(native, "_pack_mesh", timed("packing", native._pack_mesh)))
        else:
            # The v1 ABI interleaves a lazy Python projection with packing. Drain
            # exactly one original batch to separate their timings without per-face timers.
            islice = native.islice
            pack_start = 0

            def batch(*args):
                nonlocal pack_start
                start = perf_counter_ns()
                faces = tuple(islice(*args))
                ns["projection"] += perf_counter_ns() - start
                pack_start = perf_counter_ns()
                return faces

            def raster(*args):
                start = perf_counter_ns()
                ns["packing"] += start - pack_start
                ok = api(*args)
                ns["raster"] += perf_counter_ns() - start
                return ok

            hooks.enter_context(patch.object(native, "islice", batch))
            hooks.enter_context(patch.object(native, "load", lambda: raster))
        start = perf_counter_ns()
        png = render.contact_sheet(mesh, size, backend="native")
        total = perf_counter_ns() - start
    ns["other"] = total - sum(ns.values())
    return png, {key: round(value / 1e6, 4) for key, value in ns.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--profile", action="store_true", help="also measure native stages in separate passes")
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
                    reference = args.reference / "1" / "reference"
                    if not reference.is_dir():
                        reference = args.reference / "1" / "python"
                    old = image(reference / (name + ".preview.png"))
                    if pixels != old:
                        raise ValueError(f"Pixels differ from previous release: {rel}")
                first = pixels
                rows.append(dict(trial=trial + 1, model=name, backend=backend, ms=round(elapsed[0], 3)))
    report = {"exe": sys.executable, "module": model3d.__file__, "runs": rows}
    if args.profile:
        report["native_stages_ms"] = []
        for trial in range(1, 4):
            for name, spec in MODELS.items():
                mesh, _ = model3d.compile_spec(spec)
                png, stages = profile_native(mesh, 256)
                expected = workspace / "1" / ("reference" if args.reference_only else "python") / (name + ".preview.png")
                if png != expected.read_bytes():
                    raise ValueError(f"Profiled pixels differ: {name}")
                report["native_stages_ms"].append(dict(trial=trial, model=name, triangles=len(mesh.triangles), **stages))
    (workspace / "timings.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
