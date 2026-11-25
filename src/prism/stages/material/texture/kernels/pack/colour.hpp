// SHADE's colour on the pack thread: each channel times its albedo in Dst, then the
// item's rows of the three colour planes out of Dst into the out pages.
#pragma once

#include <stdint.h>

#include "vector.hpp"

namespace shade_k {

    // Row r's colour: each channel times its albedo.
    inline void colour_row(uint32_t r) {
        for (uint32_t channel = 0; channel < 3; ++channel) {
            load(L0, kVecAlbedo + 32 * channel + r);
            load(L1, kVecRed + 32 * channel + r);
            mul(L0, L1, L2);
            store(L2, kVecRed + 32 * channel + r);
        }
    }

    // Rows [first_row, end_row) coloured, once the gather's stores have landed.
    inline void colour_rows(int32_t first_row, int32_t end_row) {
        order(word(kVecAlbedo + 64 + end_row - 1) + 62);
        for (int32_t r = first_row; r < end_row; ++r) {
            colour_row(r);
        }
        tensix_sync();
    }

    // The three colour planes' words from `first_word` (`words` of them) out of Dst
    // into the item at `destination`.
    inline void colour_out(uint32_t destination, uint32_t first_word, uint32_t words) {
        for (uint32_t plane = 0; plane < kShadeColourPages; ++plane) {
            km::dst::read(
                reinterpret_cast<volatile uint32_t*>(
                    destination + 4 * (plane * kPlaneWords + first_word)
                ),
                (1 + plane) * kPlaneWords + first_word,
                words
            );
        }
    }

}  // namespace shade_k
