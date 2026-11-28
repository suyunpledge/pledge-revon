"""Optional desktop rasterizer. Only load the library shipped next to this module."""
from array import array
from functools import lru_cache
from itertools import islice
from pathlib import Path
import sysconfig


@lru_cache(maxsize=1)
def load():
    if sysconfig.get_platform() != "win-amd64":
        return None
    try:
        import ctypes as ct
        dll = ct.CDLL(str(Path(__file__).resolve().with_name("preview-win-x64.dll")))
        draw = dll.revon_draw_faces_v1
        draw.argtypes = [ct.POINTER(ct.c_double), ct.c_size_t, ct.c_int,
                         ct.POINTER(ct.c_double), ct.POINTER(ct.c_ubyte)]
        draw.restype = ct.c_int
        return draw
    except (ImportError, OSError, AttributeError):
        return None


def draw_tile(draw, faces, size, face_color):
    import ctypes as ct

    pixels = size * size
    tile = bytearray(b"\xfa\xfa\xfc") * pixels
    depth = array("d", [float("-inf")]) * pixels
    rgb_buffer = (ct.c_ubyte * len(tile)).from_buffer(tile)
    z_buffer = (ct.c_double * pixels).from_buffer(depth)
    while True:
        # Keep peak memory bounded on large meshes and preserve depth across batches.
        data = array("d")
        for a, b, c, inverse_area, lum, front in islice(faces, 1024):
            data.extend((*a, *b, *c, inverse_area, *face_color(lum, front)))
        if not data:
            return tile
        triangles = (ct.c_double * len(data)).from_buffer(data)
        if not draw(triangles, len(data) // 13, size, z_buffer, rgb_buffer):
            return None
