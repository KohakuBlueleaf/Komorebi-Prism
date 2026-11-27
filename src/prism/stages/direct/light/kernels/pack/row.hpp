// LIGHT on the pack CPU: a row's colour: the sun (its shadow's filter), the lamps,
// the specular terms, the sky, the ambient (or the field's I), emissive, background.
#pragma once

#include <stdint.h>

#include "dst.hpp"
#include "keys.hpp"
#include "tone.hpp"

namespace light_k {

    // Row k's gloss max(0, n . unit(l + v))^exponent, l in L0 to L2, the exponent by
    // squaring (prism_reference.raster.frames power, `bits` steps) into the gloss
    // vector; every LReg used.
    inline void gloss(uint32_t k, uint32_t bits) {
        for (uint32_t axis = 0; axis < 3; ++axis) {
            load(L3, sx_vector(kSxEye + axis));
            add(L0 + axis, L3, L0 + axis);
        }
        unit3(L0, L1, L2, L3, L4, L5, L6, L7);
        load(L3, plane_vector(kLvNormal, k));
        mul(L3, L0, L4);
        load(L3, plane_vector(kLvNormal + 1, k));
        TT_SFPMAD(L3, L1, L4, L4, 0);
        load(L3, plane_vector(kLvNormal + 2, k));
        TT_SFPMAD(L3, L2, L4, L4, 0);
        TTI_SFPNOP;
        at_least_zero(L4, L3);
        load(L5, plane_vector(kLvMaterial, k));
        TT_SFPSHFT(
            (-static_cast<int32_t>(kMaterialExponentShift)) & 0xFFF,
            0,
            L5,
            kShiftImmediate
        );
        add(ONE, ZERO, L6);
        immediate(L7, 1);
        for (uint32_t bit = 0; bit < bits; ++bit) {
            TT_SFPMOV(0, L5, L3, 0);
            TT_SFPAND(0, L7, L3, 0);
            TT_SFPSETCC(0, L3, 0, kNe0);
            mul(L6, L4, L6);
            TTI_SFPENCC(3, 0, 0, 10);
            if (bit + 1 < bits) {
                mul(L4, L4, L4);
                TT_SFPSHFT(0xFFF, 0, L5, kShiftImmediate);
            }
        }
        store(L6, sx_vector(kSxGloss));
    }

    // Row k's specular sum += specular x gloss x (the light's colour x `irradiance` /
    // pi): the colour's channel c the immediate light[stride c].
    inline void shine(
        uint32_t k,
        const uint32_t* light,
        uint32_t stride,
        uint32_t irradiance,
        const uint32_t* table
    ) {
        for (uint32_t channel = 0; channel < 3; ++channel) {
            load(L0, plane_vector(kLvSpecular + channel, k));
            load(L1, sx_vector(kSxGloss));
            mul(L0, L1, L0);
            immediate(L2, light[stride * channel]);
            load(L3, irradiance);
            mul(L2, L3, L2);
            immediate(L3, table[kLtInvPi]);
            mul(L2, L3, L2);
            mul(L0, L2, L0);
            load(L1, sx_vector(kSxShine + channel));
            add(L1, L0, L1);
            store(L1, sx_vector(kSxShine + channel));
        }
    }

    // The lamp's shape (prism_reference.direct.lamps shaped) on L7: t = clamp(offset -
    // scale l.axis, 0, 1), L7 x t (square (t - 1) + 1); l the unit direction to the
    // lamp in the row scratch; L0 to L6 used.
    inline void shape_row(const uint32_t* lamp) {
        for (uint32_t axis = 0; axis < 3; ++axis) {
            load(L0 + axis, sx_vector(kSxLight + axis));
        }
        immediate(L3, lamp[kLampAxis]);
        mul(L0, L3, L4);
        immediate(L3, lamp[kLampAxis + 1]);
        TT_SFPMAD(L1, L3, L4, L4, 0);
        immediate(L3, lamp[kLampAxis + 2]);
        TT_SFPMAD(L2, L3, L4, L4, 0);  // l . axis
        immediate(L3, lamp[kLampScale]);
        immediate(L5, lamp[kLampOffset]);
        mul(L3, L4, L6);
        sub(L5, L6, L6);  // offset - scale l . axis
        TTI_SFPNOP;
        at_least_zero(L6, L0);
        add(ONE, ZERO, L0);
        TTI_SFPNOP;
        TT_SFPSWAP(0, L0, L6, kMinMax);  // t = min(t, 1)
        TTI_SFPNOP;
        sub(L6, ONE, L0);
        immediate(L3, lamp[kLampSquare]);
        TT_SFPMAD(L0, L3, ONE, L0, 0);  // square (t - 1) + 1
        mul(L6, L0, L6);
        mul(L7, L6, L7);
    }

    // Row k under one lamp (prism_reference.direct.lamps point_irradiance): its
    // irradiance in the lamps' sum, with the specular term its share of the specular
    // sum.
    inline void lamp_row(
        uint32_t k,
        const uint32_t* lamp,
        const uint32_t* table,
        bool shiny,
        uint32_t bits
    ) {
        for (uint32_t axis = 0; axis < 3; ++axis) {
            immediate(L0, lamp[axis]);
            load(L1, row_vector(k, kRvPoint + axis));
            sub(L0, L1, L2 + axis);
        }
        mul(L2, L2, L5);
        TT_SFPMAD(L3, L3, L5, L5, 0);
        TT_SFPMAD(L4, L4, L5, L5, 0);  // d^2
        rsqrt_vector(L5, L6, L0, L1, L7);
        for (uint32_t axis = 0; axis < 3; ++axis) {
            mul(L2 + axis, L6, L2 + axis);
            store(L2 + axis, sx_vector(kSxLight + axis));
        }
        mul(L5, L6, L6);  // d
        load(L0, plane_vector(kLvNormal, k));
        mul(L0, L2, L7);
        load(L0, plane_vector(kLvNormal + 1, k));
        TT_SFPMAD(L0, L3, L7, L7, 0);
        load(L0, plane_vector(kLvNormal + 2, k));
        TT_SFPMAD(L0, L4, L7, L7, 0);
        TTI_SFPNOP;
        at_least_zero(L7, L0);
        immediate(L0, lamp[kLampIntensity]);
        mul(L0, L7, L7);
        immediate(L0, lamp[kLampSize2]);
        add(L5, L0, L0);
        recip(L0, L1, L2, L3, L4, L5);
        mul(L7, L1, L7);  // I max(0, n.l) / (d^2 + s^2)
        immediate(L0, lamp[kLampInvRadius]);
        mul(L6, L0, L1);
        mul(L1, L1, L1);
        mul(L1, L1, L2);
        sub(ONE, L2, L2);
        mul(L2, L2, L2);
        mul(L7, L2, L7);  // x (1 - (d / r)^4)^2
        immediate(L0, lamp[kLampRadius]);
        sub(L6, L0, L1);
        TTI_SFPNOP;
        TT_SFPSETCC(0, L1, 0, kGte0);
        add(ZERO, ZERO, L7);
        TTI_SFPENCC(3, 0, 0, 10);
        if (lamp[kLampScale] != 0) {
            shape_row(lamp);
        }
        store(L7, sx_vector(kSxE));
        for (uint32_t channel = 0; channel < 3; ++channel) {
            immediate(L0, lamp[kLampColour + channel]);
            mul(L0, L7, L0);
            load(L1, sx_vector(kSxPoints + channel));
            add(L1, L0, L1);
            store(L1, sx_vector(kSxPoints + channel));
        }
        if (shiny) {
            for (uint32_t axis = 0; axis < 3; ++axis) {
                load(L0 + axis, sx_vector(kSxLight + axis));
            }
            gloss(k, bits);
            shine(k, lamp + kLampColour, 1, sx_vector(kSxE), table);
        }
    }

    // Row k's colour: (a / pi) E + specular; emissive a; empty the background; glass:
    // tau C + that + F R in front, else C; toned (linear: not; graded: grade_row).
    template <bool glass = false>
    inline void light_row(uint32_t k, const LightNumbers& numbers, uint32_t* values) {
        const uint32_t* table = numbers.table;
        const uint32_t terms = numbers.terms;
        uint32_t mark = km::wall();
        auto lap = [&](uint32_t slot) {
            tensix_sync();
            const uint32_t now = km::wall();
            values[slot] += now - mark;
            mark = now;
        };
        TTI_SFPENCC(3, 0, 0, 10);
        if ((terms & kTermShadow) != 0) {
            // lit at a tap unless 1/z < its texel's - bias; then bilinear weights
            load(L0, row_vector(k, kRvW));
            immediate(L1, table[kLtShadowBias]);
            for (uint32_t tap = 0; tap < kLightKeys; ++tap) {
                load(L2, row_vector(k, kRvValue + tap));
                sub(L2, L1, L2);
                sub(L0, L2, L3);
                add(ONE, ZERO, L4 + tap);
                TTI_SFPNOP;
                TT_SFPSETCC(0, L3, 0, kLt0);
                add(ZERO, ZERO, L4 + tap);
                TTI_SFPENCC(3, 0, 0, 10);
            }
            load(L0, row_vector(k, kRvFx));
            sub(ONE, L0, L1);
            mul(L4, L1, L2);
            TT_SFPMAD(L5, L0, L2, L2, 0);
            mul(L6, L1, L3);
            TT_SFPMAD(L7, L0, L3, L3, 0);
            load(L0, row_vector(k, kRvFy));
            sub(ONE, L0, L1);
            mul(L2, L1, L2);
            TT_SFPMAD(L3, L0, L2, L2, 0);
            store(L2, sx_vector(kSxShadow));
            lap(kLightProfShadow);
        }
        const bool field = (terms & kTermIndirect) != 0;  // I at kSxIndirect: no sky
        load(L0, plane_vector(kLvNormal, k));
        load(L1, plane_vector(kLvNormal + 1, k));
        load(L2, plane_vector(kLvNormal + 2, k));
        if (!field) {
            mul(L0, L0, L3);
            TT_SFPMAD(L1, L1, L3, L3, kNegA);
            store(L3, sx_vector(kSxSky));
            mul(L2, L2, L3);
            store(L3, sx_vector(kSxSky + 1));
            mul(L0, L1, L3);
            store(L3, sx_vector(kSxSky + 2));
            mul(L0, L2, L3);
            store(L3, sx_vector(kSxSky + 3));
            mul(L1, L2, L3);
            store(L3, sx_vector(kSxSky + 4));
        }
        immediate(L4, table[kLtSunDirection]);
        mul(L0, L4, L3);
        immediate(L4, table[kLtSunDirection + 1]);
        TT_SFPMAD(L1, L4, L3, L3, 0);
        immediate(L4, table[kLtSunDirection + 2]);
        TT_SFPMAD(L2, L4, L3, L3, 0);
        TTI_SFPNOP;
        at_least_zero(L3, L4);
        if ((terms & kTermShadow) != 0) {
            load(L4, sx_vector(kSxShadow));
            mul(L3, L4, L3);
        }
        store(L3, sx_vector(kSxSun));
        // the kind less emissive's (0: emissive)
        load(L7, plane_vector(kLvMaterial, k));
        TT_SFPSHFT(
            (-static_cast<int32_t>(kMaterialKindShift)) & 0xFFF, 0, L7, kShiftImmediate
        );
        immediate(L6, kMaterialKindMask);
        TT_SFPAND(0, L6, L7, 0);
        TT_SFPIADD((-static_cast<int32_t>(kKindEmissive)) & 0xFFF, L7, L7, 1 | 4);
        store(L7, sx_vector(kSxKind));
        add(ZERO, ZERO, L0);
        for (uint32_t i = 0; i < 6; ++i) {
            store(L0, sx_vector(kSxPoints + i));  // and the specular sum
        }
        const bool shiny = (terms & kTermSpecular) != 0;
        const bool reflected = glass && (terms & kTermBackground) != 0;
        if (shiny || reflected) {
            const uint32_t* cam = table + kLtCamera;
            for (uint32_t axis = 0; axis < 3; ++axis) {
                immediate(L0, cam[axis]);
                load(L1, row_vector(k, kRvPoint + axis));
                sub(L0, L1, L2 + axis);
            }
            unit3(L2, L3, L4, L0, L1, L5, L6, L7);
            for (uint32_t axis = 0; axis < 3; ++axis) {
                store(L2 + axis, sx_vector(kSxEye + axis));
            }
            if (reflected) {
                // F = F0 + (1 - F0) q^5, q = 1 - max(0, n.v); times the reflection
                load(L5, plane_vector(kLvNormal, k));
                mul(L5, L2, L6);
                load(L5, plane_vector(kLvNormal + 1, k));
                TT_SFPMAD(L5, L3, L6, L6, 0);
                load(L5, plane_vector(kLvNormal + 2, k));
                TT_SFPMAD(L5, L4, L6, L6, 0);
                TTI_SFPNOP;
                at_least_zero(L6, L5);
                sub(ONE, L6, L6);
                mul(L6, L6, L7);
                mul(L7, L7, L7);
                mul(L7, L6, L7);
                immediate(L5, table[kLtFresnelRest]);
                immediate(L0, table[kLtFresnel0]);
                TT_SFPMAD(L5, L7, L0, L7, 0);
                immediate(L5, table[kLtReflection]);
                mul(L7, L5, L7);
                store(L7, sx_vector(kSxFresnel));
            }
            if (shiny) {
                for (uint32_t axis = 0; axis < 3; ++axis) {
                    immediate(L0 + axis, table[kLtSunDirection + axis]);
                }
                gloss(k, numbers.bits);
                shine(k, table + kLtSun, kLtChannel, sx_vector(kSxSun), table);
            }
            lap(kLightProfSpecular);
        }
        if ((terms & kTermLamps) != 0) {
            for (uint32_t lamp = 0; lamp < numbers.lamps; ++lamp) {
                lamp_row(
                    k, table + kLtLamp + kLampWords * lamp, table, shiny, numbers.bits
                );
            }
            lap(kLightProfLamps);
        }
        for (uint32_t channel = 0; channel < 3; ++channel) {
            const uint32_t* sky = table + kLtChannel * channel;
            if (field) {  // E = I + sun + lamps
                load(L3, sx_vector(kSxIndirect + channel));
            } else {
                load(L0, plane_vector(kLvNormal, k));
                load(L1, plane_vector(kLvNormal + 1, k));
                load(L2, plane_vector(kLvNormal + 2, k));
                immediate(L3, sky[kLtSky]);
                // K0 + KZ z z + KX (x x - y y) + (x y, x z, y z terms) + (x, y, z)
                constexpr uint32_t kScratchOf[5] = {1, 0, 2, 3, 4};
                for (uint32_t term = 0; term < 5; ++term) {
                    immediate(L4, sky[kLtSky + 1 + term]);
                    load(L5, sx_vector(kSxSky + kScratchOf[term]));
                    TT_SFPMAD(L5, L4, L3, L3, 0);
                }
                for (uint32_t axis = 0; axis < 3; ++axis) {
                    immediate(L4, sky[kLtSky + 6 + axis]);
                    TT_SFPMAD(L0 + axis, L4, L3, L3, 0);
                }
                TTI_SFPNOP;
                at_least_zero(L3, L4);
                load(L5, plane_vector(kLvVisibility, k));
                mul(L3, L5, L3);
                immediate(L4, sky[kLtAmbient]);
                add(L3, L4, L3);
            }
            immediate(L4, sky[kLtSun]);
            load(L5, sx_vector(kSxSun));
            TT_SFPMAD(L4, L5, L3, L3, 0);
            load(L4, sx_vector(kSxPoints + channel));
            add(L3, L4, L3);
            load(L5, plane_vector(kLvAlbedo + channel, k));
            immediate(L4, table[kLtInvPi]);
            mul(L5, L4, L6);
            mul(L6, L3, L3);
            load(L4, sx_vector(kSxShine + channel));
            add(L3, L4, L3);
            if (glass) {
                // (tau C + own) + F reflection R; not in front (bit 31): C
                load(L4, c_vector(channel, k));
                add(L4, L3, L3);
                if (reflected) {
                    load(L4, reflect_vector(channel, k));
                    load(L5, sx_vector(kSxFresnel));
                    mul(L5, L4, L4);
                    add(L3, L4, L3);
                }
                load(L4, c_vector(channel, k));
                load(L7, plane_vector(kLvMaterial, k));
                TT_SFPSETCC(0, L7, 0, kLt0);
                add(L4, ZERO, L3);
                TTI_SFPENCC(3, 0, 0, 10);
            } else {
                // emissive: a; empty (bit 31): the background
                load(L7, sx_vector(kSxKind));
                TT_SFPSETCC(0, L7, 0, kEq0);
                add(L5, ZERO, L3);
                TTI_SFPENCC(3, 0, 0, 10);
                if ((terms & kTermBackground) != 0) {
                    load(L4, row_vector(k, kRvValue + channel));
                } else {
                    immediate(L4, table[kLtBackground + channel]);
                }
                load(L7, plane_vector(kLvMaterial, k));
                TT_SFPSETCC(0, L7, 0, kLt0);
                add(L4, ZERO, L3);
                TTI_SFPENCC(3, 0, 0, 10);
            }
            if (numbers.mode == kLightLinear || numbers.graded) {
                store(L3, plane_vector(kLvAlbedo + channel, k));
            } else {
                tone(plane_vector(kLvAlbedo + channel, k), table);
            }
        }
        if (numbers.mode != kLightLinear && numbers.graded) {
            grade_row(k, table);
        }
        lap(kLightProfMath);
    }

}  // namespace light_k
