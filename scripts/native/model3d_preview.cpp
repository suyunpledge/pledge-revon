// Double precision and evaluation order match revon/model3d/render.py.
// The caller owns all buffers. No allocation or retained state crosses the ABI.
#include <algorithm>
#include <cmath>
#include <cstddef>

extern "C" __declspec(dllexport) int revon_draw_faces_v1(
    const double* faces, std::size_t count, int size, double* depth, unsigned char* rgb) {
    if (!faces || !depth || !rgb || size < 64 || size > 1024 || count > 1024)
        return 0;

    for (std::size_t i = 0; i < count; ++i) {
        // Screen-space XYZ for three vertices, inverse signed area, then flat RGB.
        const double* face = faces + 13 * i;
        if (!std::all_of(face, face + 10, [](double x) { return std::isfinite(x); }))
            return 0;
        const double ax = face[0], ay = face[1], az = face[2];
        const double bx = face[3], by = face[4], bz = face[5];
        const double cx = face[6], cy = face[7], cz = face[8];
        const double inverse_area = face[9];
        // Clamp in floating point before conversion, even with extreme coordinates.
        auto lower = [size](double v) { return int(std::clamp(std::floor(v), 0.0, double(size))); };
        auto upper = [size](double v) { return int(std::clamp(std::ceil(v), -1.0, double(size - 1))); };
        const int xmin = lower(std::min({ax, bx, cx})), xmax = upper(std::max({ax, bx, cx}));
        const int ymin = lower(std::min({ay, by, cy})), ymax = upper(std::max({ay, by, cy}));
        const unsigned char color[] = {static_cast<unsigned char>(face[10]),
                                       static_cast<unsigned char>(face[11]),
                                       static_cast<unsigned char>(face[12])};
        for (int y = ymin; y <= ymax; ++y) {
            const double fy = y + 0.5;
            for (int x = xmin; x <= xmax; ++x) {
                const double fx = x + 0.5;
                const double w0 = ((bx - fx) * (cy - fy) - (by - fy) * (cx - fx)) * inverse_area;
                const double w1 = ((cx - fx) * (ay - fy) - (cy - fy) * (ax - fx)) * inverse_area;
                const double w2 = 1.0 - w0 - w1;
                if (w0 < -1e-9 || w1 < -1e-9 || w2 < -1e-9)
                    continue;
                const double z = w0 * az + w1 * bz + w2 * cz;
                const int k = y * size + x;
                if (z > depth[k]) {
                    depth[k] = z;
                    std::copy_n(color, 3, rgb + 3 * k);
                }
            }
        }
    }
    return 1;
}
