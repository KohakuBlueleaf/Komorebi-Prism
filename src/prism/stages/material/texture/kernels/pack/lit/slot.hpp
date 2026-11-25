// Lit SHADE on the pack thread: a winner's slot from its first record, the material
// word, lit base, specular colour and the frame of its planes (scalar float math).
#pragma once

#include <stdint.h>

#include "../../../../../direct/light/kernels/pack/floats.hpp"
#include "../vector.hpp"

namespace shade_k {

    using fill_k::kRecCol;
    using fill_k::kRecW;
    using light_k::as_bits;
    using light_k::as_float;
    using light_k::kMagicRsqrt;

    struct Vec3 {
        float x, y, z;
    };

    inline Vec3 v3(float x, float y, float z) {
        return Vec3{x, y, z};
    }

    inline float dot(const Vec3& a, const Vec3& b) {
        return (a.x * b.x + a.y * b.y) + a.z * b.z;
    }

    inline Vec3 cross(const Vec3& a, const Vec3& b) {
        return v3(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x);
    }

    inline Vec3 scaled(const Vec3& a, float s) {
        return v3(a.x * s, a.y * s, a.z * s);
    }

    // 1 / sqrt(x), x > 0: the magic estimate and three Newton steps (the light
    // model's frame.rsqrt).
    inline float rsqrt_scalar(float x) {
        float y = as_float(kMagicRsqrt - (as_bits(x) >> 1));
        const float half = x * 0.5f;
        for (uint32_t step = 0; step < 3; ++step) {
            y = y * (1.5f - half * y * y);
        }
        return y;
    }

    inline Vec3 unit(const Vec3& v) {
        const float length2 = dot(v, v);
        return length2 > 0.0f ? scaled(v, rsqrt_scalar(length2)) : v3(0, 0, 0);
    }

    // Camera-space direction to the scene's: right x + up y + forward z.
    inline Vec3 to_world(const float* cam, const Vec3& v) {
        return v3(
            (cam[3] * v.x + cam[6] * v.y) + cam[9] * v.z,
            (cam[4] * v.x + cam[7] * v.y) + cam[10] * v.z,
            (cam[5] * v.x + cam[8] * v.y) + cam[11] * v.z
        );
    }

    // A winner's slot from its first record: material word, lit base, specular, and
    // (mapped: a normal texture, the host's frame_ok) the frame of its planes.
    inline void fill_slot(
        uint32_t* slot,
        const volatile uint32_t* record,
        uint32_t material,
        const uint32_t* material_at,
        const float* cam,
        bool mapped
    ) {
        const float f = cam[12], cx = cam[13], cy = cam[14];
        Vec3 m[3];
        for (uint32_t plane = 0; plane < 3; ++plane) {
            const uint32_t at = plane == 0 ? kRecW : kRecCol + 3 * (plane - 1);
            const float a = as_float(record[at]), b = as_float(record[at + 1]);
            m[plane] = v3(a, b, (a * cx + b * cy) + as_float(record[at + 2]));
        }
        const Vec3 normal = unit(to_world(cam, v3(-(m[0].x * f), m[0].y * f, -m[0].z)));
        const float det = dot(m[0], cross(m[1], m[2]));
        const float sign = det < 0.0f ? -1.0f : 1.0f;
        const Vec3 u_side = cross(m[2], m[0]), v_side = cross(m[0], m[1]);
        const Vec3 along_u = scaled(
            to_world(cam, v3(u_side.x, -u_side.y, u_side.z * f)), sign
        );
        const Vec3 along_v = scaled(
            to_world(cam, v3(v_side.x, -v_side.y, v_side.z * f)), sign
        );
        const float along = dot(normal, along_u);
        const Vec3 tangent = unit(
            v3(along_u.x - normal.x * along,
               along_u.y - normal.y * along,
               along_u.z - normal.z * along)
        );
        Vec3 side = cross(normal, tangent);
        if (dot(side, along_v) < 0.0f) {
            side = scaled(side, -1.0f);
        }
        const bool valid = mapped && det != 0.0f && dot(tangent, tangent) > 0.0f;
        const uint32_t kind = material_at[0] & 0xFF;
        slot[0] =
            (material | kind << kMaterialKindShift |
             (material_at[kMaterialExponent] & kExponentMax) << kMaterialExponentShift);
        for (uint32_t channel = 0; channel < 3; ++channel) {
            slot[1 + channel] = material_at[kMaterialLitBase + channel];
            slot[4 + channel] = material_at[kMaterialSpecularColour + channel];
        }
        const Vec3 frame[3] = {
            valid ? tangent : v3(0, 0, 0), valid ? side : v3(0, 0, 0), normal
        };
        for (uint32_t axis = 0; axis < 3; ++axis) {
            slot[7 + 3 * axis] = as_bits(frame[axis].x);
            slot[8 + 3 * axis] = as_bits(frame[axis].y);
            slot[9 + 3 * axis] = as_bits(frame[axis].z);
        }
    }

}  // namespace shade_k
