"""Optional desktop rasterizer. Only load the library shipped next to this module."""
from functools import lru_cache
from pathlib import Path
import struct
import sysconfig
from typing import NamedTuple


class Rasterizer(NamedTuple):
    project: object
    raster: object


@lru_cache(maxsize=1)
def load():
    if sysconfig.get_platform() != "win-amd64":
        return None
    try:
        import ctypes as ct
        dll = ct.CDLL(str(Path(__file__).resolve().with_name("preview-win-x64.dll")))
        doubles, indices, rgb = ct.POINTER(ct.c_double), ct.POINTER(ct.c_int32), ct.POINTER(ct.c_ubyte)
        project, raster = dll.revon_project_v2, dll.revon_raster_v2
        project.argtypes = [doubles, ct.c_int, indices, ct.c_int, doubles, ct.c_int, doubles, doubles, rgb]
        raster.argtypes = [doubles, ct.c_int, indices, ct.c_int, doubles, rgb, ct.c_int, doubles, rgb]
        project.restype = raster.restype = ct.c_int
        return Rasterizer(project, raster)
    except (ImportError, OSError, AttributeError):
        return None


def _pack_mesh(mesh):
    import ctypes as ct

    nv, nt = len(mesh.vertices), len(mesh.triangles)
    if max(nv, nt) > 0x7fffffff:
        return None
    xyz = (ct.c_double * (3 * nv))()
    indices = (ct.c_int32 * (3 * nt))()
    vertex, face = struct.Struct("=3d"), struct.Struct("=3i")
    try:
        for i, point in enumerate(mesh.vertices):
            vertex.pack_into(xyz, i * vertex.size, *point)
        for i, (a, b, c) in enumerate(mesh.triangles):
            # Match Python sequence indexing. The DLL validates the resulting bounds.
            face.pack_into(indices, i * face.size,
                           a if a >= 0 else nv+a, b if b >= 0 else nv+b, c if c >= 0 else nv+c)
    except (OverflowError, struct.error, ValueError, TypeError):
        return None
    return xyz, nv, indices, nt


def draw_tiles(api, mesh, bases, light, size):
    import ctypes as ct

    packed = _pack_mesh(mesh)
    if packed is None:
        return None
    xyz, nv, indices, nt = packed
    # The four cameras share an immutable mesh and reuse one view's scratch space.
    screen = (ct.c_double * (3 * nv))()
    inverse_area = (ct.c_double * nt)()
    colors = (ct.c_ubyte * (3 * nt))()
    depth = (ct.c_double * (size * size))()
    tiles = []
    for right, up, forward in bases:
        camera = (ct.c_double * 12)(*right, *up, *forward, *light)
        if not api.project(xyz, nv, indices, nt, camera, size, screen, inverse_area, colors):
            return None
        tile = bytearray(3 * size * size)
        rgb = (ct.c_ubyte * len(tile)).from_buffer(tile)
        if not api.raster(screen, nv, indices, nt, inverse_area, colors, size, depth, rgb):
            return None
        tiles.append(tile)
    return tiles
