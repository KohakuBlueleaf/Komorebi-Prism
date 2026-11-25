// SHADE's rows on the vector unit: u, v and the light divided by 1/z, a record's
// numbers into every lane, and a record's rows: texel keys, the albedo's colour, the
// marks.
#pragma once

#include <stdint.h>

#include "vector.hpp"

namespace shade_k {

    // How a record's pixels are coloured; kLightTextureMask also keys its mask's texel.
    enum Mode : uint32_t {
        kFlat,
        kLight,
        kLightTexture,
        kEmissive,
        kEmissiveTexture,
        kLightTextureMask
    };

    // Row r: covered pixels' rgb / (1/z) (q = a r, q + (a - q w) r), frac(u), 1 -
    // frac(v) (at least 0); then the depth row to 0 (no texel).
    inline void divide_row(uint32_t r) {
        TTI_SFPENCC(3, 0, 0, 10);
        load(L0, kVecTri + r);
        TT_SFPSETCC(0, L0, 0, kGte0);
        load(L1, kVecDepth + r);
        recip(L1, L2, L3, L4, L5, L6);
        for (uint32_t plane = 1; plane <= 3; ++plane) {
            load(L3, 32 * plane + r);
            mul(L3, L2, L4);
            TT_SFPMAD(L4, L1, L3, L5, kNegA);
            TT_SFPMAD(L5, L2, L4, L4, 0);
            store(L4, 32 * plane + r);
            if (plane == 1) {
                floor_to(L4, L5);
                sub(L4, L5, L4);
                TTI_SFPNOP;
                at_least_zero(L4, L5);
                store(L4, kVecS + r);
            } else if (plane == 2) {
                floor_to(L4, L5);
                sub(L4, L5, L4);
                sub(ONE, L4, L4);
                TTI_SFPNOP;
                at_least_zero(L4, L5);
                store(L4, kVecT + r);
            }
        }
        TTI_SFPENCC(3, 0, 0, 10);
        TT_SFPLOADI(L0, kFloatB, 0);
        store(L0, kVecDepth + r);
    }

    // A record's numbers to its vectors (every lane): triangle, width, width - 1,
    // height, height - 1, blocks a row, 1 + first page, base rgb, mask's pages on.
    inline void record_numbers(const uint32_t* numbers) {
        TTI_SFPENCC(3, 0, 0, 10);
        for (uint32_t i = 0; i < kRecordNumbers; ++i) {
            immediate(L0, numbers[i]);
            store(L0, kVecRecord + i);
        }
    }

    // Row r's texel keys of the record's pixels to `target` (and, kLightTextureMask,
    // the mask's key tagged to the triangle row).
    inline void key_row(uint32_t r, Mode mode, uint32_t target) {
        // x = min(floor(s width), width - 1), its block and column in the block
        load(L0, kVecS + r);
        load(L1, kVecRecord + kConstW);
        mul(L0, L1, L0);
        floor_to(L0, L2);
        load(L1, kVecRecord + kConstWLast);
        TTI_SFPNOP;
        TT_SFPSWAP(0, L1, L2, kMinMax);
        mul(L2, INV32, L3);
        floor_to(L3, L4);
        TT_SFPMAD(L4, C32, L2, L2, kNegA);
        // y likewise from 1 - t and the height
        load(L0, kVecT + r);
        load(L1, kVecRecord + kConstH);
        mul(L0, L1, L0);
        floor_to(L0, L3);
        load(L1, kVecRecord + kConstHLast);
        TTI_SFPNOP;
        TT_SFPSWAP(0, L1, L3, kMinMax);
        mul(L3, INV32, L5);
        floor_to(L5, L6);
        TT_SFPMAD(L6, C32, L3, L3, kNegA);
        // texel in the page, 1 + page; both as integers, then the key
        TT_SFPMAD(L3, C32, L2, L2, 0);
        load(L0, kVecRecord + kConstAcross);
        load(L1, kVecRecord + kConstFirst);
        TT_SFPMAD(L6, L0, L1, L6, 0);
        add(L6, L4, L6);
        if (mode == kLightTextureMask) {  // the mask's 1 + page: the same block
            load(L0, kVecRecord + kConstMask);
            add(L6, L0, L7);
        }
        add(L6, MAGIC, L6);
        add(L2, MAGIC, L2);
        TTI_SFPNOP;
        TT_SFPAND(0, MASK, L6, 0);
        TT_SFPAND(0, MASK, L2, 0);
        TT_SFPSHFT(10, 0, L6, kShiftImmediate);
        TT_SFPOR(0, L2, L6, 0);
        store(L6, target + r);
        if (mode == kLightTextureMask) {  // its key, tagged, to the triangle row
            add(L7, MAGIC, L7);
            TTI_SFPNOP;
            TT_SFPAND(0, MASK, L7, 0);
            TT_SFPSHFT(10, 0, L7, kShiftImmediate);
            TT_SFPOR(0, L2, L7, 0);
            TT_SFPLOADI(L0, kFloatB, kMinusTwo >> 16);
            TTI_SFPNOP;
            TT_SFPOR(0, L0, L7, 0);
            store(L7, kVecTri + r);
        }
    }

    // Row r's pixels: texel keys to the depth row (lit: `target`), the albedo's
    // colour; (mark) tri -2 | mask key, or `mark_bits` (glass: -2 | material).
    inline void record_row(
        uint32_t r,
        Mode mode,
        uint32_t target = kVecDepth,
        bool colour = true,
        bool mark = true,
        uint32_t mark_bits = kMinusTwo
    ) {
        load(L0, kVecTri + r);
        load(L1, kVecRecord + kConstTri);
        sub(L0, L1, L0);
        TTI_SFPNOP;
        TT_SFPSETCC(0, L0, 0, kEq0);
        const bool textured =
            (mode == kLightTexture || mode == kEmissiveTexture ||
             mode == kLightTextureMask);
        if (textured) {
            key_row(r, mode, target);
        }
        const bool lit =
            (mode == kLight || mode == kLightTexture || mode == kLightTextureMask);
        if (colour && lit) {
            load(L0, kVecBlue + r);
            for (uint32_t channel = 0; channel < 3; ++channel) {
                load(L1, kVecRecord + kConstBase + channel);
                mul(L1, L0, L2);
                store(L2, kVecRed + 32 * channel + r);
            }
        } else if (colour && (mode == kEmissive || mode == kEmissiveTexture)) {
            for (uint32_t channel = 0; channel < 3; ++channel) {
                load(L1, kVecRecord + kConstBase + channel);
                store(L1, kVecRed + 32 * channel + r);
            }
        }
        if (mark && mode != kLightTextureMask) {
            if (mark_bits == kMinusTwo) {
                TT_SFPLOADI(L0, kFloatB, kMinusTwo >> 16);
            } else {
                immediate(L0, mark_bits);
            }
            store(L0, kVecTri + r);
        }
        TTI_SFPENCC(3, 0, 0, 10);
    }

}  // namespace shade_k
