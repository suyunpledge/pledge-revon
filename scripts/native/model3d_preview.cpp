// Keep double-precision evaluation order in sync with revon/model3d/render.py.
// All buffers are caller-owned. A zero return asks the host to use its fallback.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>

struct Vec { double x, y, z; };
struct Tri { int32_t a, b, c; };
struct Color { unsigned char r, g, b; };
static_assert(sizeof(Vec) == 24 && sizeof(Tri) == 12 && sizeof(Color) == 3);

static double dot(Vec a, Vec b) { return a.x*b.x + a.y*b.y + a.z*b.z; }
static Vec sub(Vec a, Vec b) { return {a.x-b.x, a.y-b.y, a.z-b.z}; }
static Vec cross(Vec a, Vec b) {
    return {a.y*b.z-a.z*b.y, a.z*b.x-a.x*b.z, a.x*b.y-a.y*b.x};
}
static bool finite(Vec v) { return std::isfinite(v.x) && std::isfinite(v.y) && std::isfinite(v.z); }
static bool valid(Tri t, int vertices) {
    return t.a >= 0 && t.b >= 0 && t.c >= 0 && t.a < vertices && t.b < vertices && t.c < vertices;
}
static unsigned char channel(double value) { return static_cast<unsigned char>(std::min(255., value)); }

extern "C" __declspec(dllexport) int revon_project_v2(
    const Vec* vertices, int nv, const Tri* triangles, int nt, const Vec* camera,
    int size, Vec* screen, double* inverse_area, Color* colors) {
    if (size < 64 || size > 1024 || nv < 0 || nt < 0) return 0;
    if (nv == 0) return nt == 0;
    double xmin = std::numeric_limits<double>::infinity(), xmax = -xmin;
    double ymin = xmin, ymax = -ymin;
    for (int i = 0; i < nv; ++i) {
        Vec p{dot(vertices[i], camera[0]), dot(vertices[i], camera[1]), dot(vertices[i], camera[2])};
        if (!finite(p)) return 0;
        screen[i] = p;
        xmin = std::min(xmin, p.x); xmax = std::max(xmax, p.x);
        ymin = std::min(ymin, p.y); ymax = std::max(ymax, p.y);
    }
    const double dx = xmax-xmin, dy = ymax-ymin, span = std::max({dx, dy, 1e-9});
    const double scale = std::min((size-12)/std::max(dx, 1e-9*span), (size-12)/std::max(dy, 1e-9*span));
    const double ox = (size-dx*scale)/2 - xmin*scale, oy = (size-dy*scale)/2 - ymin*scale;
    for (int i = 0; i < nv; ++i) {
        Vec& p = screen[i];
        p.x = p.x*scale + ox;
        p.y = size - (p.y*scale + oy);
        if (!finite(p)) return 0;
    }
    for (int i = 0; i < nt; ++i) {
        const Tri t = triangles[i];
        if (!valid(t, nv)) return 0;
        const Vec a = screen[t.a], b = screen[t.b], c = screen[t.c];
        const double area = (b.x-a.x)*(c.y-a.y) - (b.y-a.y)*(c.x-a.x);
        inverse_area[i] = 0;
        if (std::abs(area) < 1e-12) continue;
        const Vec n = cross(sub(vertices[t.b], vertices[t.a]), sub(vertices[t.c], vertices[t.a]));
        const double length = std::sqrt(dot(n, n));
        if (length == 0) continue;
        const Vec normal{n.x/length, n.y/length, n.z/length};
        const Vec cam{dot(normal, camera[0]), dot(normal, camera[1]), dot(normal, camera[2])};
        const double lum = 0.25 + 0.75*std::abs(dot(cam, camera[3]));
        if (!std::isfinite(lum) || !std::isfinite(area)) return 0;
        inverse_area[i] = 1.0/area;
        colors[i] = cam.z >= -1e-9
            ? Color{channel(70+150*lum), channel(110+125*lum), channel(150+100*lum)}
            : Color{channel(120+135*lum), channel(30+40*lum), channel(120+135*lum)};
    }
    return 1;
}

extern "C" __declspec(dllexport) int revon_raster_v2(
    const Vec* screen, int nv, const Tri* triangles, int nt, const double* inverse_area,
    const Color* colors, int size, double* depth, Color* rgb) {
    if (size < 64 || size > 1024 || nv < 0 || nt < 0) return 0;
    std::fill_n(depth, size*size, -std::numeric_limits<double>::infinity());
    std::fill_n(rgb, size*size, Color{250, 250, 252});
    for (int i = 0; i < nt; ++i) {
        const double inv = inverse_area[i];
        if (inv == 0) continue;
        const Tri t = triangles[i];
        if (!valid(t, nv)) return 0;
        const Vec a = screen[t.a], b = screen[t.b], c = screen[t.c];
        auto lower = [size](double v) { return int(std::clamp(std::floor(v), 0.0, double(size))); };
        auto upper = [size](double v) { return int(std::clamp(std::ceil(v), -1.0, double(size-1))); };
        const int xmin = lower(std::min({a.x,b.x,c.x})), xmax = upper(std::max({a.x,b.x,c.x}));
        const int ymin = lower(std::min({a.y,b.y,c.y})), ymax = upper(std::max({a.y,b.y,c.y}));
        for (int y = ymin; y <= ymax; ++y) {
            const double fy = y + 0.5;
            for (int x = xmin; x <= xmax; ++x) {
                const double fx = x + 0.5;
                const double w0 = ((b.x-fx)*(c.y-fy) - (b.y-fy)*(c.x-fx))*inv;
                const double w1 = ((c.x-fx)*(a.y-fy) - (c.y-fy)*(a.x-fx))*inv;
                const double w2 = 1.0 - w0 - w1;
                if (w0 < -1e-9 || w1 < -1e-9 || w2 < -1e-9) continue;
                const double z = w0*a.z + w1*b.z + w2*c.z;
                const int k = y*size+x;
                if (z > depth[k]) {
                    depth[k] = z;
                    rgb[k] = colors[i];
                }
            }
        }
    }
    return 1;
}
