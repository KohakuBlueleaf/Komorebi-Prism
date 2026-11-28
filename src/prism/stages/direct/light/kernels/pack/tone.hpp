// LIGHT on the pack CPU: the command's numbers, the tone step (x / (1 + x) or
// graded: saturation, the filmic curve) and the glass's C toned alone.
#pragma once

#include <stdint.h>

#include "dst.hpp"

namespace light_k {

    // A command's numbers from the table, and its mode (kLight*, LIGHT's a9); graded:
    // a saturation other than 1 or the filmic curve (grade_row, else tone).
    struct LightNumbers {
        const uint32_t* table;
        uint32_t terms, lamps, bits, mode;
        bool graded;
#if defined(PRISM_LIGHT_TRANSMIT)
        bool transmit;  // the sun map's T weighs the shadow's taps (transmit_tile)
#endif
    };

    // x / (1 + x) of exposure x L3 into Dst vector `to` (L4 to L7, L0, L1 used).
    inline void tone(uint32_t to, const uint32_t* table) {
        immediate(L4, table[kLtExposure]);
        mul(L3, L4, L3);
        add(L3, ONE, L4);
        recip(L4, L5, L6, L7, L0, L1);
        mul(L3, L5, L6);
        store(L6, to);
    }

    // Row k's linear colour in a's rows toned (prism_reference.post.tone): exposure,
    // saturation s (not 1: max(0, lum + (x - lum) s)), the curve: x / (1 + x), filmic
    // at most 1, or none (view).
    __attribute__((noinline)) void grade_row(uint32_t k, const uint32_t* table) {
        TTI_SFPENCC(3, 0, 0, 10);
        immediate(L7, table[kLtExposure]);
        for (uint32_t channel = 0; channel < 3; ++channel) {
            load(L0 + channel, plane_vector(kLvAlbedo + channel, k));
            mul(L0 + channel, L7, L0 + channel);
        }
        if (table[kLtSaturation] != kOneBits) {
            immediate(L4, kLumaBits[0]);
            mul(L0, L4, L3);
            for (uint32_t channel = 1; channel < 3; ++channel) {
                immediate(L4, kLumaBits[channel]);
                TT_SFPMAD(L0 + channel, L4, L3, L3, 0);
            }
            immediate(L4, table[kLtSaturation]);
            for (uint32_t channel = 0; channel < 3; ++channel) {
                sub(L0 + channel, L3, L0 + channel);
                TT_SFPMAD(L0 + channel, L4, L3, L0 + channel, 0);
                TTI_SFPNOP;
                at_least_zero(L0 + channel, L5);
            }
        }
        for (uint32_t channel = 0; channel < 3; ++channel) {
            store(L0 + channel, plane_vector(kLvAlbedo + channel, k));
        }
        if (table[kLtCurve] == kCurveView) {
            return;
        }
        const bool filmic = table[kLtCurve] == kCurveFilmic;
        for (uint32_t channel = 0; channel < 3; ++channel) {
            load(L3, plane_vector(kLvAlbedo + channel, k));
            if (filmic) {
                // x (a x + b) over x (c x + d) + e, at most 1
                immediate(L4, kFilmicA);
                immediate(L5, kFilmicB);
                TT_SFPMAD(L3, L4, L5, L4, 0);
                mul(L3, L4, L2);
                immediate(L4, kFilmicC);
                immediate(L5, kFilmicD);
                TT_SFPMAD(L3, L4, L5, L4, 0);
                immediate(L5, kFilmicE);
                TT_SFPMAD(L3, L4, L5, L4, 0);
                recip(L4, L5, L6, L7, L0, L1);
                mul(L2, L5, L3);
                immediate(L4, kOneBits);
                TTI_SFPNOP;
                TT_SFPSWAP(0, L4, L3, kMinMax);
                store(L3, plane_vector(kLvAlbedo + channel, k));
            } else {
                add(L3, ONE, L4);
                recip(L4, L5, L6, L7, L0, L1);
                mul(L3, L5, L6);
                store(L6, plane_vector(kLvAlbedo + channel, k));
            }
        }
    }

    // Glass, rows [first, end) of a quarter where the glass is nowhere in front: C
    // toned into a's rows (tone, or grade_row; out of line, as the glass's other code).
    __attribute__((noinline)) void tone_rows(
        uint32_t first, uint32_t end, const uint32_t* table, bool graded
    ) {
        TTI_SFPENCC(3, 0, 0, 10);
        for (uint32_t k = first; k < end; ++k) {
            for (uint32_t channel = 0; channel < 3; ++channel) {
                load(L3, c_vector(channel, k));
                if (graded) {
                    store(L3, plane_vector(kLvAlbedo + channel, k));
                } else {
                    tone(plane_vector(kLvAlbedo + channel, k), table);
                }
            }
            if (graded) {
                grade_row(k, table);
            }
        }
    }

}  // namespace light_k
