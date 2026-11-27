// A map's 2 x 2 taps on the pack CPU's vector unit (pack_sfpu: L11 to L14 as its
// setup leaves them): from a point through one map's camera (the map's numbers the
// same in every lane), or from map coordinates whose map's numbers are lanes' own.
#pragma once

#include <stdint.h>

#include "../../../../core/include/sfpu.hpp"

namespace shadow_share {

    using namespace pack_sfpu;

    constexpr uint32_t kTaps = 4;
    constexpr uint32_t kLess0 = 0;          // SFPSETCC: lanes below 0
    constexpr uint32_t kHalfHigh = 0x3F00;  // 0.5's upper half
    constexpr uint32_t kAllLanes = 10;      // SFPENCC: every lane enabled
    constexpr uint32_t kPageShift = 10;     // a key: page << 10 | texel

    // A number of the map: the same in every lane (its float's bits).
    struct Bits {
        uint32_t bits;

        void into(uint32_t lreg) const {
            immediate(lreg, bits);
        }
    };

    // A number of the map: each lane's own (a Dst vector).
    struct Lanes {
        uint32_t vector;

        void into(uint32_t lreg) const {
            load(lreg, vector);
        }
    };

    // Where a lookup's results go: the fractions, two scratch vectors for the corner,
    // the four keys (consecutive vectors, tap t = dx + 2 dy).
    struct Out {
        uint32_t fx, fy, corner, keys;
    };

    // L5 = the key (1 + page) << 10 | texel of column L0, row L1 (floats, kept) of a
    // map in 32 x 32 pages, `first` the first page + 1, `across` pages a row; L2 to
    // L7 used.
    template <class First, class Across>
    inline void tap_key(const First& first, const Across& across) {
        mul(L0, INV32, L2);
        floor_to(L2, L3);
        TT_SFPMAD(L3, C32, L0, L2, kNegA);  // the column in its page
        mul(L1, INV32, L4);
        floor_to(L4, L5);
        TT_SFPMAD(L5, C32, L1, L4, kNegA);  // the row in its page
        TT_SFPMAD(L4, C32, L2, L4, 0);      // the texel in its page
        across.into(L6);
        first.into(L7);
        TT_SFPMAD(L5, L6, L7, L5, 0);
        add(L5, L3, L5);  // 1 + page
        add(L5, MAGIC, L5);
        add(L4, MAGIC, L4);
        TTI_SFPNOP;
        TT_SFPAND(0, MASK, L5, 0);
        TT_SFPAND(0, MASK, L4, 0);
        TT_SFPSHFT(kPageShift, 0, L5, kShiftImmediate);
        TT_SFPOR(0, L4, L5, 0);
    }

    // From map coordinates sx in L2, sy in L3 (texels, a texel's centre at + 0.5):
    // the fractions, the 2 x 2 taps' keys into `out` (0 for a tap outside the map of
    // `width` x `height` texels); L0 to L7 used.
    template <class First, class Across, class Width, class Height>
    inline void coordinate_taps(
        const Out& out,
        const First& first,
        const Across& across,
        const Width& width,
        const Height& height
    ) {
        TT_SFPLOADI(L1, kFloatB, kHalfHigh);
        sub(L2, L1, L2);
        sub(L3, L1, L3);
        floor_to(L2, L4);
        floor_to(L3, L5);
        sub(L2, L4, L2);
        sub(L3, L5, L3);
        store(L2, out.fx);
        store(L3, out.fy);
        store(L4, out.corner);
        store(L5, out.corner + 1);
        for (uint32_t tap = 0; tap < kTaps; ++tap) {
            load(L0, out.corner);
            load(L1, out.corner + 1);
            if ((tap & 1) != 0) {
                add(L0, ONE, L0);
            }
            if ((tap & 2) != 0) {
                add(L1, ONE, L1);
            }
            tap_key(first, across);
            for (uint32_t axis = 0; axis < 2; ++axis) {
                if (axis == 0) {
                    width.into(L6);
                } else {
                    height.into(L6);
                }
                TT_SFPSETCC(0, L0 + axis, 0, kLess0);
                add(ZERO, ZERO, L5);
                TTI_SFPENCC(3, 0, 0, kAllLanes);
                sub(L0 + axis, L6, L7);
                TTI_SFPNOP;
                TT_SFPSETCC(0, L7, 0, kGte0);
                add(ZERO, ZERO, L5);
                TTI_SFPENCC(3, 0, 0, kAllLanes);
            }
            store(L5, out.keys + tap);
        }
    }

    // The coordinates of the lanes' points (the vectors point[3], normal[3]) moved
    // `texel` (world size, float bits) along the normal, by the map's `camera` (its 16
    // words): 1/z into the vector `w`, sx in L2, sy in L3; L0 to L7 used. Recip(a, y,
    // four work LRegs): y = 1 / a, correctly rounded.
    template <void (*Recip)(uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t)>
    inline void project(
        const uint32_t (&point)[3],
        const uint32_t (&normal)[3],
        const uint32_t* camera,
        uint32_t texel,
        uint32_t w
    ) {
        // d = (P + n texel) - eye, along right, up, forward
        immediate(L7, texel);
        for (uint32_t axis = 0; axis < 3; ++axis) {
            load(L0, point[axis]);
            load(L1, normal[axis]);
            TT_SFPMAD(L1, L7, L0, L0, 0);
            immediate(L1, camera[axis]);
            sub(L0, L1, L0);
            for (uint32_t along = 0; along < 3; ++along) {
                immediate(L1, camera[3 + 3 * along + axis]);
                if (axis == 0) {
                    mul(L0, L1, L2 + along);
                } else {
                    TT_SFPMAD(L0, L1, L2 + along, L2 + along, 0);
                }
            }
        }
        Recip(L4, L5, L0, L1, L6, L7);
        store(L5, w);
        // sx = cx + f x w, sy = cy - f y w
        mul(L2, L5, L2);
        mul(L3, L5, L3);
        immediate(L0, camera[12]);
        immediate(L1, camera[13]);
        TT_SFPMAD(L0, L2, L1, L2, 0);
        immediate(L1, camera[14]);
        TT_SFPMAD(L0, L3, L1, L3, kNegA);
    }

    // The 2 x 2 taps of the lanes' points through one map whose numbers are the same
    // in every lane: its camera, normal offset `texel`, first page + 1, pages across,
    // width and height (float bits); 1/z into `w`, the rest into `out`.
    template <void (*Recip)(uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t)>
    inline void point_taps(
        const uint32_t (&point)[3],
        const uint32_t (&normal)[3],
        const uint32_t* camera,
        uint32_t texel,
        uint32_t first,
        uint32_t across,
        uint32_t width,
        uint32_t height,
        uint32_t w,
        const Out& out
    ) {
        project<Recip>(point, normal, camera, texel, w);
        coordinate_taps(out, Bits{first}, Bits{across}, Bits{width}, Bits{height});
    }

}  // namespace shadow_share
