// LIGHT on the pack CPU: the indirect field at a row's points: the cell, the
// corners' keys, the trilinear weights, each axis's blend, I.
#pragma once

#include <stdint.h>

#include "dst.hpp"

namespace light_k {

    // Row k's field cell (indirect lookup): g = (P + n h/2 - origin) / h - 1/2 a axis
    // (one remainder step), floor(g) at kSfBase, g - floor(g) at kSfT; all LRegs.
    inline void field_point(uint32_t k, const uint32_t* table) {
        TTI_SFPENCC(3, 0, 0, 10);
        for (uint32_t axis = 0; axis < 3; ++axis) {
            immediate(L6, table[kLtFieldShift]);
            immediate(L7, table[kLtFieldInverse]);
            load(L0, row_vector(k, kRvPoint + axis));
            load(L1, plane_vector(kLvNormal + axis, k));
            TT_SFPMAD(L1, L6, L0, L0, 0);
            immediate(L1, table[kLtFieldOrigin + axis]);
            sub(L0, L1, L0);
            mul(L0, L7, L2);
            immediate(L3, table[kLtFieldSpacing]);
            TT_SFPMAD(L2, L3, L0, L3, kNegA);
            TT_SFPMAD(L3, L7, L2, L2, 0);
            TT_SFPLOADI(L3, kFloatB, kHalfB);
            sub(L2, L3, L2);
            floor_to(L2, L4);
            sub(L2, L4, L2);
            store(L4, sx_vector(kSfBase + axis));
            store(L2, sx_vector(kSfT + axis));
        }
    }

    // Row k's corner keys at kSfKey (c: cell + (c & 1, c >> 1 & 1, c >> 2)): (1 + page)
    // << 10 | the voxel's direction-0 texel; 0 off the grid and on an empty pixel.
    __attribute__((noinline)) void field_keys(uint32_t k, const uint32_t* table) {
        field_point(k, table);
        // per axis and cell: block = floor(i / block side), the page term block x its
        // stride, the texel term (i - block x side) x its stride; off the grid -2^21
        const uint32_t inverse[3] = {kEighthBits, 0x3F000000, kEighthBits};
        const uint32_t side[3] = {kEightBits, kTwoBits, kEightBits};
        const uint32_t page_stride[3] = {
            kOneBits, table[kLtFieldLayer], table[kLtFieldAcross]
        };
        const uint32_t texel_stride[3] = {kOneBits, kSixtyFourBits, kEightBits};
        for (uint32_t axis = 0; axis < 3; ++axis) {
            for (uint32_t cell = 0; cell < 2; ++cell) {
                load(L0, sx_vector(kSfBase + axis));
                if (cell != 0) {
                    add(L0, ONE, L0);
                }
                immediate(L1, inverse[axis]);
                mul(L0, L1, L1);
                floor_to(L1, L2);
                immediate(L3, side[axis]);
                TT_SFPMAD(L2, L3, L0, L3, kNegA);
                immediate(L4, texel_stride[axis]);
                mul(L3, L4, L3);
                immediate(L4, page_stride[axis]);
                mul(L2, L4, L2);
                immediate(L5, kOutsideBits);
                immediate(L6, table[kLtFieldDims + axis]);
                sub(L0, L6, L6);
                TTI_SFPNOP;
                TT_SFPSETCC(0, L0, 0, kLt0);
                add(L5, ZERO, L2);
                TTI_SFPENCC(3, 0, 0, 10);
                TT_SFPSETCC(0, L6, 0, kGte0);
                add(L5, ZERO, L2);
                TTI_SFPENCC(3, 0, 0, 10);
                store(L2, sx_vector(kSfPage + 2 * axis + cell));
                store(L3, sx_vector(kSfTerm + 2 * axis + cell));
            }
        }
        immediate(L7, table[kLtFieldFirst]);
        for (uint32_t corner = 0; corner < kFieldCorners; ++corner) {
            const uint32_t cell[3] = {corner & 1, corner >> 1 & 1, corner >> 2};
            load(L0, sx_vector(kSfPage + cell[0]));
            load(L1, sx_vector(kSfPage + 2 + cell[1]));
            add(L0, L1, L0);
            load(L1, sx_vector(kSfPage + 4 + cell[2]));
            add(L0, L1, L0);
            add(L0, L7, L0);  // 1 + page, negative off the grid
            load(L1, sx_vector(kSfTerm + cell[0]));
            load(L2, sx_vector(kSfTerm + 2 + cell[1]));
            add(L1, L2, L1);
            load(L2, sx_vector(kSfTerm + 4 + cell[2]));
            add(L1, L2, L1);
            add(L0, MAGIC, L2);
            add(L1, MAGIC, L3);
            TTI_SFPNOP;
            TT_SFPAND(0, MASK, L2, 0);
            TT_SFPAND(0, MASK, L3, 0);
            TT_SFPSHFT(10, 0, L2, kShiftImmediate);
            TT_SFPOR(0, L3, L2, 0);
            TT_SFPSETCC(0, L0, 0, kLt0);
            add(ZERO, ZERO, L2);
            TTI_SFPENCC(3, 0, 0, 10);
            store(L2, sx_vector(kSfKey + corner));
        }
        add(ZERO, ZERO, L4);
        load(L0, plane_vector(kLvMaterial, k));
        TT_SFPSETCC(0, L0, 0, kLt0);
        for (uint32_t corner = 0; corner < kFieldCorners; ++corner) {
            store(L4, sx_vector(kSfKey + corner));
        }
        TTI_SFPENCC(3, 0, 0, 10);
    }

    // Row k before its texels: the cell's fractions t, the corners' trilinear weights
    // at kSfWeight, the totals 0.
    __attribute__((noinline)) void field_weights(uint32_t k, const uint32_t* table) {
        field_point(k, table);
        for (uint32_t axis = 0; axis < 3; ++axis) {
            load(L0 + axis, sx_vector(kSfT + axis));
            sub(ONE, L0 + axis, L3 + axis);
        }
        for (uint32_t corner = 0; corner < kFieldCorners; ++corner) {
            const uint32_t x = (corner & 1) != 0 ? L0 : L3;
            const uint32_t y = (corner >> 1 & 1) != 0 ? L1 : L4;
            const uint32_t z = (corner >> 2) != 0 ? L2 : L5;
            mul(x, y, L6);
            mul(L6, z, L6);
            store(L6, sx_vector(kSfWeight + corner));
        }
        add(ZERO, ZERO, L7);
        for (uint32_t i = 0; i < 4; ++i) {
            store(L7, sx_vector(kSfTotal + i));
        }
    }

    // Row k, an axis's texels at kSfTexel: over corners with data, sum w code^2 a
    // channel and sum w; where any, totals += n_a^2 / sum w x the sums, axes += n_a^2.
    __attribute__((noinline)) void field_blend(uint32_t k, uint32_t axis) {
        constexpr uint32_t kShift[3] = {20, 9, 0};
        constexpr uint32_t kMask[3] = {0x7FF, 0x7FF, 0x1FF};
        TTI_SFPENCC(3, 0, 0, 10);
        add(ZERO, ZERO, L0);
        add(ZERO, ZERO, L1);
        add(ZERO, ZERO, L2);
        add(ZERO, ZERO, L3);
        for (uint32_t corner = 0; corner < kFieldCorners; ++corner) {
            load(L4, sx_vector(kSfWeight + corner));
            load(L5, sx_vector(kSfTexel + corner));
            TT_SFPSETCC(0, L5, 0, kLt0);
            add(L3, L4, L3);
            for (uint32_t channel = 0; channel < 3; ++channel) {
                // the code as a float: its bits under 1.5 x 2^23's, less 1.5 x 2^23
                TT_SFPMOV(0, L5, L6, 0);
                if (kShift[channel] != 0) {
                    TT_SFPSHFT(
                        (-static_cast<int32_t>(kShift[channel])) & 0xFFF,
                        0,
                        L6,
                        kShiftImmediate
                    );
                }
                immediate(L7, kMask[channel]);
                TT_SFPAND(0, L7, L6, 0);
                TT_SFPOR(0, MAGIC, L6, 0);
                sub(L6, MAGIC, L6);
                mul(L6, L6, L6);
                TT_SFPMAD(L6, L4, L0 + channel, L0 + channel, 0);
            }
            TTI_SFPENCC(3, 0, 0, 10);
        }
        for (uint32_t channel = 0; channel < 3; ++channel) {
            store(L0 + channel, sx_vector(kSfNum + channel));
        }
        recip(L3, L4, L5, L6, L7, L0);
        load(L5, plane_vector(kLvNormal + axis, k));
        mul(L5, L5, L5);
        mul(L5, L4, L4);  // n_a^2 / the weights' sum
        TTI_SFPNOP;
        TT_SFPSETCC(0, L3, 0, kNe0);
        for (uint32_t channel = 0; channel < 3; ++channel) {
            load(L6, sx_vector(kSfNum + channel));
            mul(L4, L6, L6);
            load(L7, sx_vector(kSfTotal + channel));
            add(L7, L6, L7);
            store(L7, sx_vector(kSfTotal + channel));
        }
        load(L7, sx_vector(kSfTotal + 3));
        add(L7, L5, L7);
        store(L7, sx_vector(kSfTotal + 3));
        TTI_SFPENCC(3, 0, 0, 10);
    }

    // Row k's I at kSxIndirect: the totals over the axes' sum, each channel times its
    // (1 / max code)^2 x scale; where no axis found data, ambient.
    __attribute__((noinline)) void field_finish(const uint32_t* table) {
        TTI_SFPENCC(3, 0, 0, 10);
        load(L0, sx_vector(kSfTotal + 3));
        recip(L0, L1, L2, L3, L4, L5);
        for (uint32_t channel = 0; channel < 3; ++channel) {
            load(L2, sx_vector(kSfTotal + channel));
            mul(L2, L1, L2);
            immediate(L3, table[kLtFieldUnit + channel]);
            mul(L2, L3, L2);
            store(L2, sx_vector(kSxIndirect + channel));
        }
        TTI_SFPNOP;
        TT_SFPSETCC(0, L0, 0, kEq0);
        for (uint32_t channel = 0; channel < 3; ++channel) {
            immediate(L2, table[kLtChannel * channel + kLtAmbient]);
            store(L2, sx_vector(kSxIndirect + channel));
        }
        TTI_SFPENCC(3, 0, 0, 10);
    }

}  // namespace light_k
