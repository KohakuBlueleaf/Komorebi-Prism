// Triangle setup and pixel fill of the rasterizer, as prism_reference.raster has them.
// float32 only, no fused multiply-add (build with -ffp-contract=off / --fmad=false).
#pragma once

#include <cmath>
#include <cstdint>

#include "kr.hpp"

#ifdef __CUDACC__
#define KR_NOINLINE __noinline__
#else
#define KR_NOINLINE inline
#endif

namespace kr {

    struct Mesh {
        const float* positions;  // (V, 3)
        const float* colors;     // (V, 3)
        const int32_t* indices;  // (T, 3)
        float camera[16];
        int triangle_count;
    };

    // One setup record: what the fill needs of one triangle.
    struct Record {
        int32_t triangle;           // triangle index, -1 when dropped
        int32_t box[4];             // pixel box x0, x1, y0, y1 (inclusive)
        float a[3], b[3], c[3];     // edge values  a x + b y + c
        uint32_t top_left;          // bit i: edge i is a top or left edge
        float inverse_z_plane[3];   // 1/z plane
        float colour_planes[3][3];  // colour planes [x, y, 1][channel]
    };

    // Camera-space x, y, z (along right, up, forward) of `point`, as in
    // prism_reference.raster.setup.
    KR_HD inline void camera_space(
        const float* camera, const float* point, float* camera_point
    ) {
        float offset_x = point[0] - camera[0];
        float offset_y = point[1] - camera[1];
        float offset_z = point[2] - camera[2];
        camera_point[0] =
            ((offset_x * camera[3] + offset_y * camera[4]) + offset_z * camera[5]);
        camera_point[1] =
            ((offset_x * camera[6] + offset_y * camera[7]) + offset_z * camera[8]);
        camera_point[2] =
            ((offset_x * camera[9] + offset_y * camera[10]) + offset_z * camera[11]);
    }

    // Screen x, y and 1/z of a camera-space point beyond the near distance.
    KR_HD inline void to_screen(
        const float* camera, const float* point, float* screen
    ) {
        float inverse_z = 1.0f / point[2];
        screen[0] = camera[13] + camera[12] * (point[0] * inverse_z);
        screen[1] = camera[14] - camera[12] * (point[1] * inverse_z);
        screen[2] = inverse_z;
    }

    KR_HD inline float plane(
        const float* coefficients, const float* values, float inverse_area
    ) {
        return (
            ((coefficients[0] * values[0] + coefficients[1] * values[1]) +
             coefficients[2] * values[2]) *
            inverse_area
        );
    }

    // Fills `record` for the piece with `screen` corners (x, y, 1/z) and `colours` of
    // `triangle`; record.triangle stays -1 when it covers no pixel centre box.
    KR_HD inline void build_record(
        float screen[3][3], float colours[3][3], int triangle, Record& record
    ) {
        record.triangle = -1;
        float area2 = (screen[1][0] - screen[0][0]) * (screen[2][1] - screen[0][1]);
        area2 = area2 - (screen[2][0] - screen[0][0]) * (screen[1][1] - screen[0][1]);
        if (area2 == 0.0f) {
            return;
        }
        if (area2 < 0.0f) {
            for (int axis = 0; axis < 3; axis++) {
                float swapped = screen[1][axis];
                screen[1][axis] = screen[2][axis];
                screen[2][axis] = swapped;
                float swapped_colour = colours[1][axis];
                colours[1][axis] = colours[2][axis];
                colours[2][axis] = swapped_colour;
            }
            area2 = -area2;
        }
        float lo_x = fminf(fminf(screen[0][0], screen[1][0]), screen[2][0]);
        float hi_x = fmaxf(fmaxf(screen[0][0], screen[1][0]), screen[2][0]);
        float lo_y = fminf(fminf(screen[0][1], screen[1][1]), screen[2][1]);
        float hi_y = fmaxf(fmaxf(screen[0][1], screen[1][1]), screen[2][1]);
        record.box[0] = (int)fminf(fmaxf(ceilf(lo_x - 0.5f), 0.0f), (float)WIDTH);
        record.box[1] = ((int)fmaxf(
            fminf(floorf(hi_x - 0.5f), (float)(WIDTH - 1)), -1.0f
        ));
        record.box[2] = (int)fminf(fmaxf(ceilf(lo_y - 0.5f), 0.0f), (float)HEIGHT);
        record.box[3] = ((int)fmaxf(
            fminf(floorf(hi_y - 0.5f), (float)(HEIGHT - 1)), -1.0f
        ));
        if (record.box[0] > record.box[1] || record.box[2] > record.box[3]) {
            return;
        }
        record.top_left = 0;
        for (int i = 0; i < 3; i++) {
            int start = (i + 1) % 3, end = (i + 2) % 3;
            record.a[i] = screen[start][1] - screen[end][1];
            record.b[i] = screen[end][0] - screen[start][0];
            record.c[i] = (-(
                record.a[i] * screen[start][0] + record.b[i] * screen[start][1]
            ));
            if (record.a[i] > 0.0f || (record.a[i] == 0.0f && record.b[i] > 0.0f)) {
                record.top_left |= 1u << i;
            }
        }
        float inverse_area = 1.0f / area2;
        float inverse_zs[3] = {screen[0][2], screen[1][2], screen[2][2]};
        record.inverse_z_plane[0] = plane(record.a, inverse_zs, inverse_area);
        record.inverse_z_plane[1] = plane(record.b, inverse_zs, inverse_area);
        record.inverse_z_plane[2] = plane(record.c, inverse_zs, inverse_area);
        for (int channel = 0; channel < 3; channel++) {
            float channel_values[3] = {
                colours[0][channel], colours[1][channel], colours[2][channel]
            };
            record.colour_planes[0][channel] = (plane(
                record.a, channel_values, inverse_area
            ));
            record.colour_planes[1][channel] = (plane(
                record.b, channel_values, inverse_area
            ));
            record.colour_planes[2][channel] = (plane(
                record.c, channel_values, inverse_area
            ));
        }
        record.triangle = triangle;
    }

    // The one or two pieces of `triangle`, `corners` (x, y, z, colour) in camera space,
    // cut at z = near (raster.setup.clip_polygon); out of line for the GPU.
    KR_HD KR_NOINLINE int clip_triangle(
        const float* camera,
        const float (*corners)[6],
        int triangle,
        Record& first,
        Record& second
    ) {
        const float near = camera[15];
        float poly[4][6];
        int vertex_count = 0;
        for (int corner = 0; corner < 3; corner++) {
            const float* from_corner = corners[corner];
            const float* to_corner = corners[(corner + 1) % 3];
            bool from_inside = from_corner[2] > near, to_inside = to_corner[2] > near;
            if (from_inside) {
                for (int component = 0; component < 6; component++) {
                    poly[vertex_count][component] = from_corner[component];
                }
                vertex_count++;
            }
            if (from_inside != to_inside) {
                const float* inside = from_inside ? from_corner : to_corner;
                const float* outside = from_inside ? to_corner : from_corner;
                float fraction = (near - inside[2]) / (outside[2] - inside[2]);
                for (int component = 0; component < 6; component++) {
                    poly[vertex_count][component] =
                        (inside[component] +
                         fraction * (outside[component] - inside[component]));
                }
                poly[vertex_count][2] = near;
                vertex_count++;
            }
        }
        for (int piece = 0; piece + 2 < vertex_count; piece++) {
            const int fan[3] = {0, piece + 1, piece + 2};
            float screen[3][3], colours[3][3];
            for (int i = 0; i < 3; i++) {
                to_screen(camera, poly[fan[i]], screen[i]);
                for (int channel = 0; channel < 3; channel++) {
                    colours[i][channel] = poly[fan[i]][3 + channel];
                }
            }
            build_record(screen, colours, triangle, piece == 0 ? first : second);
        }
        return (
            (first.triangle >= 0 ? 1 : 0) |
            (vertex_count == 4 && second.triangle >= 0 ? 2 : 0)
        );
    }

    // Fills `first` (and `second`) with the pieces of `triangle`, whole or clipped at
    // z = near. Returns bit 0 when `first` holds a piece, bit 1 for `second`.
    KR_HD inline int setup_triangle(
        const Mesh& mesh, int triangle, Record& first, Record& second
    ) {
        first.triangle = -1;
        float corners[3][6];
        int vertex_indices[3], beyond = 0;
        for (int i = 0; i < 3; i++) {
            vertex_indices[i] = mesh.indices[3 * triangle + i];
            camera_space(
                mesh.camera, mesh.positions + 3 * vertex_indices[i], corners[i]
            );
            beyond += corners[i][2] > mesh.camera[15];
        }
        if (beyond == 0) {
            return 0;
        }
        for (int i = 0; i < 3; i++) {
            for (int channel = 0; channel < 3; channel++) {
                corners[i][3 + channel] = mesh.colors[3 * vertex_indices[i] + channel];
            }
        }
        if (beyond < 3) {
            return clip_triangle(mesh.camera, corners, triangle, first, second);
        }
        float screen[3][3], colours[3][3];
        for (int i = 0; i < 3; i++) {
            to_screen(mesh.camera, corners[i], screen[i]);
            for (int channel = 0; channel < 3; channel++) {
                colours[i][channel] = corners[i][3 + channel];
            }
        }
        build_record(screen, colours, triangle, first);
        return first.triangle >= 0 ? 1 : 0;
    }

    // True when the pixel centre (px, py) is inside the triangle (top-left fill rule).
    KR_HD inline bool covers(const Record& record, float px, float py) {
        for (int i = 0; i < 3; i++) {
            float edge_value = (record.a[i] * px + record.b[i] * py) + record.c[i];
            if (!(edge_value > 0.0f ||
                  (edge_value == 0.0f && ((record.top_left >> i) & 1u)))) {
                return false;
            }
        }
        return true;
    }

    KR_HD inline float depth_at(const Record& record, float px, float py) {
        return (
            (record.inverse_z_plane[0] * px + record.inverse_z_plane[1] * py) +
            record.inverse_z_plane[2]
        );
    }

    KR_HD inline bool nearer(float inverse_z, int triangle, float depth, int owner) {
        return inverse_z > depth || (inverse_z == depth && triangle < owner);
    }

    KR_HD inline void colour_at(
        const Record& record, float px, float py, float* colour
    ) {
        for (int channel = 0; channel < 3; channel++) {
            colour[channel] =
                ((record.colour_planes[0][channel] * px +
                  record.colour_planes[1][channel] * py) +
                 record.colour_planes[2][channel]);
        }
    }

    KR_HD inline float background(int channel) {
        return channel == 2 ? 0.08f : 0.05f;
    }

}  // namespace kr
