// LIGHT on the pack CPU: Dst for a quarter tile (its planes, rows' vectors, the
// scratch), the numbers the row's steps share, a float's bits, rsqrt.
#pragma once

#include <stdint.h>

#include <riscv_vector.h>

#include "../../../../../core/include/sfpu.hpp"
#include "../../../../../core/include/surface.h"
#include "../../../../../core/include/texel_pages/pages.hpp"
#include "../../../../../core/include/texel_pages/protocol.h"
#include "../from_raster.hpp"
#include "../light.h"
#include "floats.hpp"

namespace light_k {

    using namespace pack_sfpu;
    using namespace texel_pages;
    using fill_k::kOutPageBytes;
    using fill_k::kPlanes;
    using setup_k::setup_pass::recip;

    // Dst for a quarter tile: its planes (row k of plane p at kLightRows p + k), each
    // row's vectors (kRv*), the lanes' column + 0.5, (px - cx) / f, 1 / f, the scratch.
    constexpr uint32_t kLightRows = 8;
    constexpr uint32_t kLvAlbedo = 0, kLvMaterial = 3, kLvNormal = 4, kLvVisibility = 7;
    constexpr uint32_t kLvSpecular = 8, kLvDepth = 11, kLvPlanes = 12;
    constexpr uint32_t kLightKeys = 4;
    // a row's: four texels (keys until gathered), the filter's fractions, 1/z, point
    constexpr uint32_t kRvValue = 0, kRvFx = 4, kRvFy = 5, kRvW = 6, kRvPoint = 7;
    constexpr uint32_t kRowVectors = 10;
    constexpr uint32_t kGlassKeys = 3;  // the reflection's texels (glass_vector)
    constexpr uint32_t kLvRow = kLightRows * kLvPlanes;
    constexpr uint32_t kLvLane = kLvRow + kLightRows * kRowVectors;
    constexpr uint32_t kLvXTerm = kLvLane + 1, kLvInvF = kLvLane + 2;
    constexpr uint32_t kLvScratch = kLvLane + 3;
    // Row scratch: sky, max(0, n.s), shadow, eye, lamps, specular, lamp l and E,
    // gloss, corner, view (glass: mirror) direction, kind - 4, glass F reflection.
    constexpr uint32_t kSxSky = 0;
    constexpr uint32_t kSxSun = 5;
    constexpr uint32_t kSxShadow = 6;
    constexpr uint32_t kSxEye = 7;
    constexpr uint32_t kSxPoints = 10;
    constexpr uint32_t kSxShine = 13, kSxLight = 16, kSxE = 19, kSxGloss = 20;
    constexpr uint32_t kSxCorner = 21, kSxDirection = 23, kSxKind = 26;
    constexpr uint32_t kSxFresnel = 27;
    constexpr uint32_t kScratchVectors = 28;
    constexpr uint32_t
        kSxIndirect = kSxSky;  // the field's I r, g, b (no sky term then)
    // glass: tau C (C where the glass is not in front), plane c's row k at kLvC + 8 c +
    // k (an even vector: its rows are 256 words in the window, as a plane's)
    constexpr uint32_t kLvC = (kLvScratch + kScratchVectors + 1) & ~1u;
    // glass: the reflection's red, green, blue texels (keys until gathered), as tau C
    constexpr uint32_t kLvReflect = kLvC + 3 * kLightRows;
    static_assert(kLvReflect + kGlassKeys * kLightRows <= 256);
    // each Dst plane's page in the item (mover_a/items.hpp)
    constexpr uint32_t kLightSource[kLvPlanes] = {0, 1, 2, 11, 3, 4, 5, 6, 7, 8, 9, 10};
    constexpr uint32_t kLt0 = 0, kNe0 = 2;                            // SFPSETCC
    constexpr uint32_t kZeroTexel = kShadeSlots * kTexPageBytes + 4;  // after the white
    // The field (kTermIndirect) in the row scratch, its scan: corner keys, page and
    // texel terms per axis and cell, the cell, the fractions; I at the sky's place.
    constexpr uint32_t kSfKey = 0, kSfPage = 8, kSfTerm = 14, kSfBase = 20, kSfT = 23;
    // its gather: an axis's texels (then sums r, g, b), weights, totals (r, g, b, axes)
    constexpr uint32_t kSfTexel = 0, kSfNum = 0, kSfWeight = 8, kSfTotal = 16;
    constexpr uint32_t kFieldCorners = 8;
    // a corner's texel address in the light work's words (32 a row, 1,024 a corner)
    constexpr uint32_t kLwField = 8192;
    static_assert(4 * (kLwField + 1024 * kFieldCorners) <= kLightWorkBytes);
    // a texel of direction d is 4 x 128 d bytes after direction 0's (light.h kField*)
    constexpr uint32_t kFieldDirectionBytes = 4 * kFieldDirectionTexels;
    static_assert(
        kZeroTexel + 5 * kFieldDirectionBytes < (kShadeSlots + 1) * kTexPageBytes
    );
#if defined(PRISM_LIGHT_TRANSMIT)
    // T's texel of a key 0 (off the map): every byte 255, after the field's zeros
    constexpr uint32_t kOneTexel = kZeroTexel + 6 * kFieldDirectionBytes;
    static_assert(kOneTexel + 4 <= (kShadeSlots + 1) * kTexPageBytes);
    // a row's T at its taps in the row scratch, over the lamps' and the specular
    // vectors (kSxPoints to kSxGloss, made after the shadow) and the field's corner
    // (used before it): tap t of channel c at kSxTransmit + 4 c + t
    constexpr uint32_t kSxTransmit = kSxPoints;
    static_assert(kSxTransmit + 3 * kLightKeys <= kSxCorner + 1);
    // T's taps' words (their texel addresses, then their codes), 1,024 a tap
    constexpr uint32_t kTransmitWords = 1024 * kLightKeys;

    // T's numbers of a tile (Pass::transmit_tile), after its taps' words: on, 1 + its
    // first light page, the map's 1 + first page, its blocks a page's shift, a byte's
    // mask and a word's shift in a texel's place, a code's mask and its spread.
    struct TransmitTile {
        uint32_t on, first, map_first, page_shift, byte_mask, word_shift, mask, spread;
    };

    constexpr uint32_t kTransmitAllWords = kTransmitWords + sizeof(TransmitTile) / 4;
    // in the light work, after the field's corners (before the profile's words; the
    // tile thread's light step asks for a larger work)
    constexpr uint32_t kLwTransmit = kLwField + 1024 * kFieldCorners;
    static_assert(kLwTransmit + kTransmitAllWords <= kLwProfile);

    // A float of `bits` made in a register (no constant in local memory).
    inline float held_float(uint32_t bits) {
        asm volatile("" : "+r"(bits));
        return as_float(bits);
    }
#endif
    constexpr uint32_t kOutsideBits = 0xCA000000;  // -2^21: a page term off the grid
    constexpr uint32_t kEighthBits = 0x3E000000, kEightBits = 0x41000000;  // 1/8, 8
    constexpr uint32_t kTwoBits = 0x40000000;  // 2 (1/2: kHalfB)
    constexpr uint32_t kOneBits = 0x3F800000, kSixtyFourBits = 0x42800000;  // 1, 64
    // the tone step's numbers (prism_reference.post.tone TONE_LUMA, FILMIC), float32
    // bits
    constexpr uint32_t kLumaBits[3] = {0x3E59B3D0, 0x3F371759, 0x3D93DD98};
    constexpr uint32_t kFilmicA = 0x4020A3D7, kFilmicB = 0x3CF5C28F;  // 2.51, 0.03
    constexpr uint32_t kFilmicC = 0x401B851F, kFilmicD = 0x3F170A3D;  // 2.43, 0.59
    constexpr uint32_t kFilmicE = 0x3E0F5C29;                         // 0.14

    constexpr uint32_t plane_vector(uint32_t plane, uint32_t k) {
        return kLightRows * plane + k;
    }

    constexpr uint32_t row_vector(uint32_t k, uint32_t at) {
        return kLvRow + kRowVectors * k + at;
    }

    constexpr uint32_t sx_vector(uint32_t at) {
        return kLvScratch + at;
    }

    constexpr uint32_t c_vector(uint32_t channel, uint32_t k) {
        return kLvC + kLightRows * channel + k;
    }

    constexpr uint32_t reflect_vector(uint32_t channel, uint32_t k) {
        return kLvReflect + kLightRows * channel + k;
    }

    // row k's texel `tap`: the shadow's four, then (glass) the reflection's three
    constexpr uint32_t tap_vector(uint32_t k, uint32_t tap) {
        return (
            tap < kLightKeys ? row_vector(k, kRvValue + tap)
                             : reflect_vector(tap - kLightKeys, k)
        );
    }

}  // namespace light_k
