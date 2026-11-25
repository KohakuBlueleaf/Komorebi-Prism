// SHADE of the rasterizer, as prism_reference.raster.frames has it: the setup of a
// triangle's material values and the colour of one pixel. float32 only, no fused
// multiply-add (build with -ffp-contract=off).
#pragma once

#include <cmath>
#include <cstdint>

#include "fill.hpp"

namespace kr {

    // SHADE, as raster.frames has it: the kinds' codes, texture slots, the
    // lit kind's weights and the alpha byte under which a masked pixel is a hole.
    constexpr int KIND_FLAT = 0;
    constexpr int KIND_TEXTURED = 1;
    constexpr int KIND_MASKED = 2;
    constexpr int KIND_LIT = 3;
    constexpr int KIND_EMISSIVE = 4;
    constexpr int SLOT_ALBEDO = 0;
    constexpr int SLOT_MASK = 1;
    constexpr int SLOT_NORMAL = 2;
    constexpr int SLOT_SPECULAR = 3;
    constexpr int SLOTS = 4;
    constexpr int MIP_LEVELS = 11;
    constexpr float AMBIENT = 0.25f;
    constexpr float DIFFUSE = 0.75f;
    constexpr int OPAQUE_BYTE = 128;

    // A scene's materials file (prism_reference.scene.public.materials), by triangle
    // and by material.
    struct Materials {
        const float* uv;           // (T, 3, 2)
        const int32_t* material;   // (T,)
        const float* light;        // (T, 3) light term per corner
        const int32_t* kind;       // (M,)
        const float* base_colour;  // (M, 3)
        const int32_t* textures;   // (M, SLOTS), -1 for none
        const int32_t* exponent;   // (M,)
        const float* specular;     // (M, 3)
        const uint8_t* texels;     // RGBA8 of every level of every texture
        const int64_t* mip;        // (N, MIP_LEVELS, 3) offset, width, height
        const int32_t* levels;     // (N,)
        const float* linear;       // (256,) albedo byte to linear colour
    };

    // What SHADE needs of one triangle.
    struct ShadeTriangle {
        int32_t valid;         // the triangle has a kept piece
        float planes[3][3];    // [x, y, 1][u, v, light term] times 1/z
        int32_t level[SLOTS];  // mip level per texture slot
        float frame[3][3];     // tangent, bitangent, normal facing the eye
        int32_t frame_ok;      // the coordinates give a tangent
    };

    KR_HD inline float dot3(const float* a, const float* b) {
        return (a[0] * b[0] + a[1] * b[1]) + a[2] * b[2];
    }

    KR_HD inline void cross3(const float* a, const float* b, float* out) {
        out[0] = a[1] * b[2] - a[2] * b[1];
        out[1] = a[2] * b[0] - a[0] * b[2];
        out[2] = a[0] * b[1] - a[1] * b[0];
    }

    // v / |v| in place; zero where |v| is zero.
    KR_HD inline void normalize3(float* v) {
        float length = sqrtf(dot3(v, v));
        for (int k = 0; k < 3; k++) {
            v[k] = length > 0.0f ? v[k] / length : 0.0f;
        }
    }

    // The first piece of `triangle` setup keeps, its corners' (u, v, light term) in
    // `values`, the planes of value / z in record.colour_planes and its doubled area.
    KR_HD inline bool shade_piece(
        const Mesh& mesh,
        const Materials& materials,
        int triangle,
        Record& record,
        float values[3][3],
        float& area2
    ) {
        const float near = mesh.camera[15];
        float corners[3][6];
        int beyond = 0;
        for (int i = 0; i < 3; i++) {
            int vertex = mesh.indices[3 * triangle + i];
            camera_space(mesh.camera, mesh.positions + 3 * vertex, corners[i]);
            corners[i][3] = materials.uv[6 * triangle + 2 * i];
            corners[i][4] = materials.uv[6 * triangle + 2 * i + 1];
            corners[i][5] = materials.light[3 * triangle + i];
            beyond += corners[i][2] > near;
        }
        if (beyond == 0) {
            return false;
        }
        float poly[4][6];
        int vertex_count = 0;
        if (beyond == 3) {
            for (int i = 0; i < 3; i++) {
                for (int component = 0; component < 6; component++) {
                    poly[i][component] = corners[i][component];
                }
            }
            vertex_count = 3;
        } else {
            for (int corner = 0; corner < 3; corner++) {
                const float* from_corner = corners[corner];
                const float* to_corner = corners[(corner + 1) % 3];
                bool from_inside = from_corner[2] > near;
                bool to_inside = to_corner[2] > near;
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
        }
        for (int piece = 0; piece + 2 < vertex_count; piece++) {
            const int fan[3] = {0, piece + 1, piece + 2};
            float screen[3][3], weighted[3][3];
            for (int i = 0; i < 3; i++) {
                to_screen(mesh.camera, poly[fan[i]], screen[i]);
                for (int j = 0; j < 3; j++) {
                    values[i][j] = poly[fan[i]][3 + j];
                    weighted[i][j] = values[i][j] * screen[i][2];
                }
            }
            area2 = (screen[1][0] - screen[0][0]) * (screen[2][1] - screen[0][1]);
            area2 =
                (area2 - (screen[2][0] - screen[0][0]) * (screen[1][1] - screen[0][1]));
            if (area2 < 0.0f) {
                for (int j = 0; j < 3; j++) {
                    float swapped = values[1][j];
                    values[1][j] = values[2][j];
                    values[2][j] = swapped;
                }
                area2 = -area2;
            }
            build_record(screen, weighted, triangle, record);
            if (record.triangle >= 0) {
                return true;
            }
        }
        return false;
    }

    // SHADE's setup of one triangle (raster.frames.shade_setup).
    KR_HD inline void shade_setup_triangle(
        const Mesh& mesh, const Materials& materials, int triangle, ShadeTriangle& out
    ) {
        Record record;
        float values[3][3], area2;
        out.valid = shade_piece(mesh, materials, triangle, record, values, area2);
        const int32_t*
            texture = (materials.textures + SLOTS * materials.material[triangle]);
        for (int slot = 0; slot < SLOTS; slot++) {
            out.level[slot] = 0;
        }
        if (out.valid) {
            for (int k = 0; k < 3; k++) {
                for (int j = 0; j < 3; j++) {
                    out.planes[k][j] = record.colour_planes[k][j];
                }
            }
            float du1 = values[1][0] - values[0][0], dv1 = values[1][1] - values[0][1];
            float du2 = values[2][0] - values[0][0], dv2 = values[2][1] - values[0][1];
            float uv_area2 = fabsf(du1 * dv2 - du2 * dv1);
            for (int slot = 0; slot < SLOTS; slot++) {
                if (texture[slot] < 0) {
                    continue;
                }
                const int64_t*
                    size = (materials.mip + (int64_t)texture[slot] * MIP_LEVELS * 3);
                float texels = uv_area2 * (float)(size[1] * size[2]);
                int levels = materials.levels[texture[slot]];
                for (int k = 1; k < levels; k++) {
                    out.level[slot] += texels > area2 * ldexpf(1.0f, 2 * k - 1);
                }
            }
        }
        float p[3][3], uv[3][2];
        for (int i = 0; i < 3; i++) {
            int vertex = mesh.indices[3 * triangle + i];
            for (int k = 0; k < 3; k++) {
                p[i][k] = mesh.positions[3 * vertex + k];
            }
            uv[i][0] = materials.uv[6 * triangle + 2 * i];
            uv[i][1] = materials.uv[6 * triangle + 2 * i + 1];
        }
        float e1[3], e2[3], to_eye[3], normal[3];
        for (int k = 0; k < 3; k++) {
            e1[k] = p[1][k] - p[0][k];
            e2[k] = p[2][k] - p[0][k];
            to_eye[k] = mesh.camera[k] - p[0][k];
        }
        cross3(e1, e2, normal);
        normalize3(normal);
        if (dot3(normal, to_eye) < 0.0f) {
            for (int k = 0; k < 3; k++) {
                normal[k] = -normal[k];
            }
        }
        float du1 = uv[1][0] - uv[0][0], dv1 = uv[1][1] - uv[0][1];
        float du2 = uv[2][0] - uv[0][0], dv2 = uv[2][1] - uv[0][1];
        float det = du1 * dv2 - du2 * dv1;
        float sign = det < 0.0f ? -1.0f : 1.0f;
        float tangent[3], bitangent[3], side[3];
        for (int k = 0; k < 3; k++) {
            tangent[k] = (e1[k] * dv2 - e2[k] * dv1) * sign;
            bitangent[k] = (e2[k] * du1 - e1[k] * du2) * sign;
        }
        float along = dot3(normal, tangent);
        for (int k = 0; k < 3; k++) {
            tangent[k] = tangent[k] - normal[k] * along;
        }
        normalize3(tangent);
        cross3(normal, tangent, side);
        if (dot3(side, bitangent) < 0.0f) {
            for (int k = 0; k < 3; k++) {
                side[k] = -side[k];
            }
        }
        for (int k = 0; k < 3; k++) {
            out.frame[0][k] = tangent[k];
            out.frame[1][k] = side[k];
            out.frame[2][k] = normal[k];
        }
        out.frame_ok = det != 0.0f && dot3(tangent, tangent) > 0.0f;
    }

    // The texel nearest to (u, v) of a level, coordinates wrapping; row 0 is v = 1.
    KR_HD inline const uint8_t* fetch(
        const Materials& materials, int texture, int level, float u, float v
    ) {
        const int64_t*
            entry = (materials.mip + ((int64_t)texture * MIP_LEVELS + level) * 3);
        int64_t width = entry[1], height = entry[2];
        float s = u - floorf(u);
        float t = v - floorf(v);
        if (!(s - s == 0.0f)) {  // not finite
            s = 0.0f;
        }
        if (!(t - t == 0.0f)) {
            t = 0.0f;
        }
        int64_t x = (int64_t)(s * (float)width);
        int64_t y = (int64_t)((1.0f - t) * (float)height);
        x = x < width - 1 ? x : width - 1;
        y = y < height - 1 ? y : height - 1;
        return materials.texels + entry[0] + (y * width + x) * 4;
    }

    KR_HD inline float unit_texel(uint8_t byte) {
        return (float)(byte / 255.0);
    }

    KR_HD inline float signed_texel(uint8_t byte) {
        return (float)(byte * 2.0 / 255.0 - 1.0);
    }

    // x ** exponent for exponent >= 1, by squaring (low bit first).
    KR_HD inline float power(float x, int exponent) {
        float result = 1.0f, base = x;
        while (exponent > 0) {
            if (exponent & 1) {
                result = result * base;
            }
            base = base * base;
            exponent >>= 1;
        }
        return result;
    }

    // SHADE of one pixel (raster.frames.shade_layer): `colour` holds FILL's
    // colour and is replaced unless the kind is flat; returns true for a hole.
    KR_HD inline bool shade_pixel(
        const Mesh& mesh,
        const Materials& materials,
        const float* light_position,
        const ShadeTriangle& prepared,
        int triangle,
        float inverse_z,
        float px,
        float py,
        float* colour
    ) {
        int material = materials.material[triangle];
        int kind = materials.kind[material];
        if (kind == KIND_FLAT) {
            return false;
        }
        const float (*plane)[3] = prepared.planes;
        float u = ((plane[0][0] * px + plane[1][0] * py) + plane[2][0]) / inverse_z;
        float v = ((plane[0][1] * px + plane[1][1] * py) + plane[2][1]) / inverse_z;
        float light = ((plane[0][2] * px + plane[1][2] * py) + plane[2][2]) / inverse_z;
        const int32_t* texture = materials.textures + SLOTS * material;
        const float* base = materials.base_colour + 3 * material;
        const uint8_t* albedo_texel = nullptr;
        if (texture[SLOT_ALBEDO] >= 0) {
            albedo_texel = (fetch(
                materials, texture[SLOT_ALBEDO], prepared.level[SLOT_ALBEDO], u, v
            ));
        }
        float albedo[3];
        for (int c = 0; c < 3; c++) {
            albedo[c] =
                (albedo_texel ? materials.linear[albedo_texel[c]] * base[c] : base[c]);
        }
        if (kind == KIND_EMISSIVE) {
            for (int c = 0; c < 3; c++) {
                colour[c] = albedo[c];
            }
            return false;
        }
        if (kind != KIND_LIT) {
            for (int c = 0; c < 3; c++) {
                colour[c] = albedo[c] * light;
            }
            if (kind != KIND_MASKED) {
                return false;
            }
            uint8_t alpha = albedo_texel ? albedo_texel[3] : 255;
            if (texture[SLOT_MASK] >= 0) {
                alpha = (fetch(
                    materials, texture[SLOT_MASK], prepared.level[SLOT_MASK], u, v
                )[3]);
            }
            return alpha < OPAQUE_BYTE;
        }
        const float* camera = mesh.camera;
        float z = 1.0f / inverse_z;
        float xc = ((px - camera[13]) / camera[12]) * z;
        float yc = ((camera[14] - py) / camera[12]) * z;
        float to_light[3], to_eye[3], half[3], normal[3];
        for (int k = 0; k < 3; k++) {
            float position =
                (((camera[k] + camera[3 + k] * xc) + camera[6 + k] * yc) +
                 camera[9 + k] * z);
            to_light[k] = light_position[k] - position;
            to_eye[k] = camera[k] - position;
        }
        normalize3(to_light);
        normalize3(to_eye);
        for (int k = 0; k < 3; k++) {
            half[k] = to_light[k] + to_eye[k];
        }
        normalize3(half);
        const float (*frame)[3] = prepared.frame;
        if (texture[SLOT_NORMAL] >= 0 && prepared.frame_ok) {
            const uint8_t* n = (fetch(
                materials, texture[SLOT_NORMAL], prepared.level[SLOT_NORMAL], u, v
            ));
            float nx = signed_texel(n[0]), ny = signed_texel(n[1]);
            float nz = signed_texel(n[2]);
            for (int k = 0; k < 3; k++) {
                normal[k] = (frame[0][k] * nx + frame[1][k] * ny) + frame[2][k] * nz;
            }
            normalize3(normal);
        } else {
            for (int k = 0; k < 3; k++) {
                normal[k] = frame[2][k];
            }
        }
        float diffuse = fmaxf(dot3(normal, to_light), 0.0f);
        float gloss = (power(
            fmaxf(dot3(normal, half), 0.0f), materials.exponent[material]
        ));
        const float* specular = materials.specular + 3 * material;
        const uint8_t* specular_texel = nullptr;
        if (texture[SLOT_SPECULAR] >= 0) {
            specular_texel = (fetch(
                materials, texture[SLOT_SPECULAR], prepared.level[SLOT_SPECULAR], u, v
            ));
        }
        for (int c = 0; c < 3; c++) {
            float strength =
                (specular_texel ? specular[c] * unit_texel(specular_texel[c])
                                : specular[c]);
            colour[c] = albedo[c] * (AMBIENT + DIFFUSE * diffuse) + strength * gloss;
        }
        return false;
    }

}  // namespace kr
