// LIGHT on the pack CPU: a row's scene point and its texel keys (the shadow's four
// taps, the background's, glass: the mirrored view's), by the vector unit.
#pragma once

#include <stdint.h>

#include "../../../shadow_pcf/kernels/share.hpp"
#include "dst.hpp"

namespace light_k {

    // q = a / f for `a` (kept): a times 1 / f, then one step on the remainder a - q f.
    inline void over_focal(
        uint32_t a, uint32_t q, uint32_t f, uint32_t inverse, uint32_t f_bits
    ) {
        load(inverse, kLvInvF);
        mul(a, inverse, q);
        immediate(f, f_bits);
        TT_SFPMAD(q, f, a, f, kNegA);
        TT_SFPMAD(f, inverse, q, q, 0);
    }

    // x, y, z over their length (rsqrt); length2, inverse and three work LRegs.
    inline void unit3(
        uint32_t x,
        uint32_t y,
        uint32_t z,
        uint32_t length2,
        uint32_t inverse,
        uint32_t work0,
        uint32_t work1,
        uint32_t work2
    ) {
        mul(x, x, length2);
        TT_SFPMAD(y, y, length2, length2, 0);
        TT_SFPMAD(z, z, length2, length2, 0);
        rsqrt_vector(length2, inverse, work0, work1, work2);
        mul(x, inverse, x);
        mul(y, inverse, y);
        mul(z, inverse, z);
    }

    // L5 = the key (1 + page) << 10 | texel of column L0, row L1 (floats, kept) of a
    // map in 32 x 32 pages from first - 1, `across` a row (float bits); L2 to L7 used.
    inline void tap_key(uint32_t first_bits, uint32_t across_bits) {
        mul(L0, INV32, L2);
        floor_to(L2, L3);
        TT_SFPMAD(L3, C32, L0, L2, kNegA);  // the column in its page
        mul(L1, INV32, L4);
        floor_to(L4, L5);
        TT_SFPMAD(L5, C32, L1, L4, kNegA);  // the row in its page
        TT_SFPMAD(L4, C32, L2, L4, 0);      // the texel in its page
        immediate(L6, across_bits);
        immediate(L7, first_bits);
        TT_SFPMAD(L5, L6, L7, L5, 0);
        add(L5, L3, L5);  // 1 + page
        add(L5, MAGIC, L5);
        add(L4, MAGIC, L4);
        TTI_SFPNOP;
        TT_SFPAND(0, MASK, L5, 0);
        TT_SFPAND(0, MASK, L4, 0);
        TT_SFPSHFT(10, 0, L5, kShiftImmediate);
        TT_SFPOR(0, L4, L5, 0);
    }

    // Row k: the point, shadow taps' keys, 1/z, fractions; empty: background key;
    // glass: keys of the mirrored view (glass_over), all 0 where not in front.
    template <bool glass = false>
    inline void light_keys(
        uint32_t k, const uint32_t* table, uint32_t numerator_bits, uint32_t terms
    ) {
        const uint32_t* cam = table + kLtCamera;
        const uint32_t* sun = table + kLtShadowCamera;
        TTI_SFPENCC(3, 0, 0, 10);
        immediate(L0, numerator_bits);
        over_focal(L0, L1, L2, L3, cam[12]);  // (cy - py) / f
        // the view direction (forward + right sx) - up sy, sy = -(cy - py) / f
        load(L0, kLvXTerm);
        for (uint32_t axis = 0; axis < 3; ++axis) {
            immediate(L2, cam[9 + axis]);
            immediate(L3, cam[3 + axis]);
            TT_SFPMAD(L3, L0, L2, L2, 0);
            immediate(L3, cam[6 + axis]);
            TT_SFPMAD(L3, L1, L2, L2, 0);
            store(L2, sx_vector(kSxDirection + axis));
        }
        // the point: z = 1 / w, ((eye + right xc) + up yc) + forward z
        load(L2, plane_vector(kLvDepth, k));
        recip(L2, L3, L4, L5, L6, L7);
        mul(L0, L3, L0);
        mul(L1, L3, L1);
        for (uint32_t axis = 0; axis < 3; ++axis) {
            immediate(L2, cam[axis]);
            immediate(L4, cam[3 + axis]);
            TT_SFPMAD(L4, L0, L2, L2, 0);
            immediate(L4, cam[6 + axis]);
            TT_SFPMAD(L4, L1, L2, L2, 0);
            immediate(L4, cam[9 + axis]);
            TT_SFPMAD(L4, L3, L2, L2, 0);
            store(L2, row_vector(k, kRvPoint + axis));
        }
        if ((terms & kTermShadow) != 0) {
            // the sun's map: its 2 x 2 taps' keys, 1/z, fractions (shadow_share)
            const uint32_t point[3] = {
                row_vector(k, kRvPoint),
                row_vector(k, kRvPoint + 1),
                row_vector(k, kRvPoint + 2),
            };
            const uint32_t normal[3] = {
                plane_vector(kLvNormal, k),
                plane_vector(kLvNormal + 1, k),
                plane_vector(kLvNormal + 2, k),
            };
            const shadow_share::Out out = {
                row_vector(k, kRvFx),
                row_vector(k, kRvFy),
                sx_vector(kSxCorner),
                row_vector(k, kRvValue),
            };
            shadow_share::point_taps<recip>(
                point,
                normal,
                sun,
                table[kLtShadowTexel],
                table[kLtShadowFirst],
                table[kLtShadowAcross],
                table[kLtShadowSide],
                table[kLtShadowSide],
                row_vector(k, kRvW),
                out
            );
        } else {
            add(ZERO, ZERO, L0);
            for (uint32_t tap = 0; tap < kLightKeys; ++tap) {
                store(L0, row_vector(k, kRvValue + tap));
            }
        }
        if (glass && (terms & kTermBackground) != 0) {
            // v = unit(eye - P), 2 max(0, n.v) n - v in place of the view direction
            for (uint32_t axis = 0; axis < 3; ++axis) {
                immediate(L0, cam[axis]);
                load(L1, row_vector(k, kRvPoint + axis));
                sub(L0, L1, L2 + axis);
            }
            unit3(L2, L3, L4, L0, L1, L5, L6, L7);
            load(L0, plane_vector(kLvNormal, k));
            mul(L0, L2, L5);
            load(L0, plane_vector(kLvNormal + 1, k));
            TT_SFPMAD(L0, L3, L5, L5, 0);
            load(L0, plane_vector(kLvNormal + 2, k));
            TT_SFPMAD(L0, L4, L5, L5, 0);
            TTI_SFPNOP;
            at_least_zero(L5, L0);
            add(L5, L5, L5);  // 2 (n.v), exact
            for (uint32_t axis = 0; axis < 3; ++axis) {
                load(L0, plane_vector(kLvNormal + axis, k));
                TT_SFPMAD(L0, L5, L2 + axis, L6, kNegC);
                store(L6, sx_vector(kSxDirection + axis));
            }
        }
        add(ZERO, ZERO, L5);
        add(ZERO, ZERO, L6);
        add(ZERO, ZERO, L7);
        if ((terms & kTermBackground) != 0) {
            // the view direction turned by -turn about y (prism_reference.direct.sky
            // background): (c x + s z, y, c z - s x), each product and sum rounded on
            // its own
            load(L0, sx_vector(kSxDirection));
            load(L2, sx_vector(kSxDirection + 2));
            immediate(L3, table[kLtTurnCos]);
            immediate(L4, table[kLtTurnSin]);
            mul(L3, L0, L5);
            mul(L4, L2, L6);
            add(L5, L6, L5);
            mul(L3, L2, L6);
            mul(L4, L0, L7);
            sub(L6, L7, L6);
            store(L5, sx_vector(kSxDirection));
            store(L6, sx_vector(kSxDirection + 2));
            // (u, v) = (x, z) / (|x| + |y| + |z|), each by its reciprocal and a step
            load(L0, sx_vector(kSxDirection));
            load(L1, sx_vector(kSxDirection + 1));
            load(L2, sx_vector(kSxDirection + 2));
            TTI_SFPABS(0, L0, L3, 1);
            TTI_SFPABS(0, L1, L4, 1);
            add(L3, L4, L3);
            TTI_SFPABS(0, L2, L4, 1);
            add(L3, L4, L3);
            recip(L3, L4, L5, L6, L7, L1);
            mul(L0, L4, L5);
            TT_SFPMAD(L5, L3, L0, L6, kNegA);
            TT_SFPMAD(L6, L4, L5, L5, 0);
            load(L0, sx_vector(kSxDirection + 2));
            mul(L0, L4, L6);
            TT_SFPMAD(L6, L3, L0, L7, kNegA);
            TT_SFPMAD(L7, L4, L6, L6, 0);
            // where y < 0: ((1 - |v|) sign u, (1 - |u|) sign v)
            TTI_SFPNOP;
            TTI_SFPABS(0, L6, L0, 1);
            sub(ONE, L0, L0);
            TTI_SFPABS(0, L5, L2, 1);
            sub(ONE, L2, L2);
            TTI_SFPNOP;
            TT_SFPSETCC(0, L5, 0, kLt0);
            TT_SFPMAD(L0, ONE, ZERO, L0, kNegA);
            TTI_SFPENCC(3, 0, 0, 10);
            TT_SFPSETCC(0, L6, 0, kLt0);
            TT_SFPMAD(L2, ONE, ZERO, L2, kNegA);
            TTI_SFPENCC(3, 0, 0, 10);
            load(L1, sx_vector(kSxDirection + 1));
            TT_SFPSETCC(0, L1, 0, kLt0);
            add(L0, ZERO, L5);
            add(L2, ZERO, L6);
            TTI_SFPENCC(3, 0, 0, 10);
            // column, row: floor((t + 1) / 2 x side), at most side - 1, at least 0
            TT_SFPLOADI(L7, kFloatB, kHalfB);
            immediate(L4, table[kLtOctaSide]);
            add(L5, ONE, L5);
            mul(L5, L7, L5);
            mul(L5, L4, L5);
            add(L6, ONE, L6);
            mul(L6, L7, L6);
            mul(L6, L4, L6);
            floor_to(L5, L0);
            floor_to(L6, L1);
            for (uint32_t axis = 0; axis < 2; ++axis) {
                immediate(L4, table[kLtOctaLast]);
                TTI_SFPNOP;
                TT_SFPSWAP(0, L4, L0 + axis, kMinMax);
                at_least_zero(L0 + axis, L4);
            }
            tap_key(table[kLtOctaFirst], table[kLtOctaAcross]);
            immediate(L4, table[kLtOctaChannel]);
            TT_SFPMOV(0, L5, L6, 0);
            TT_SFPIADD(0, L4, L6, 4);
            TT_SFPMOV(0, L6, L7, 0);
            TT_SFPIADD(0, L4, L7, 4);
        }
        if (glass) {  // the reflection's keys; every key 0 where not in front
            store(L5, reflect_vector(0, k));
            store(L6, reflect_vector(1, k));
            store(L7, reflect_vector(2, k));
            add(ZERO, ZERO, L4);
            load(L0, plane_vector(kLvMaterial, k));
            TT_SFPSETCC(0, L0, 0, kLt0);
            for (uint32_t tap = 0; tap < kLightKeys; ++tap) {
                store(L4, row_vector(k, kRvValue + tap));
            }
            for (uint32_t tap = 0; tap < kGlassKeys; ++tap) {
                store(L4, reflect_vector(tap, k));
            }
            TTI_SFPENCC(3, 0, 0, 10);
            return;
        }
        // an empty pixel's keys (bit 31 of its material word)
        add(ZERO, ZERO, L4);
        load(L0, plane_vector(kLvMaterial, k));
        TT_SFPSETCC(0, L0, 0, kLt0);
        store(L5, row_vector(k, kRvValue));
        store(L6, row_vector(k, kRvValue + 1));
        store(L7, row_vector(k, kRvValue + 2));
        store(L4, row_vector(k, kRvValue + 3));
        TTI_SFPENCC(3, 0, 0, 10);
    }

}  // namespace light_k
