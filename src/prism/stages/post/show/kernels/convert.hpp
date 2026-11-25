// SHOW's conversion on mover B: the thresholds of the 8-bit rule, their buckets, and a
// tile's rows of three colour planes (the Dst window's order) as R, G, B, 255 pixels.
#pragma once

#include <stdint.h>

#include "../../../raster/kernels/common/layouts.hpp"

namespace show_k {
#include "show.h"

    using fill_k::kPlaneWords;

    // The word of (row, column) of a plane in the Dst window's order: vector v, lane l
    // at 64 (v / 2) + 16 (l / 8) + 2 (l mod 8) + v mod 2.
    inline uint32_t window_word(uint32_t row, uint32_t column) {
        return 64 * (row / 2) + row % 2 + 16 * (column / 8) + 2 * (column % 8);
    }

    // The 8-bit value of a float32 colour: the thresholds at or under its bits (word
    // k: the smallest float32 of value k), found from `buckets`; under `first` (word
    // 1) 0.
    inline uint32_t show_byte(
        const int32_t* thresholds,
        int32_t first,
        const tt_l1_ptr uint8_t* buckets,
        uint32_t bits
    ) {
        const int32_t value = static_cast<int32_t>(bits);
        if (value < first) {
            return 0;
        }
        if (value >= static_cast<int32_t>(kShowOne)) {
            return kShowTableWords - 1;
        }
        uint32_t index = buckets[(bits - kShowBucketBase) >> kShowBucketShift];
        while (index < kShowTableWords - 1 && value >= thresholds[index + 1]) {
            ++index;
        }
        return index;
    }

    // The table's words (L1 at `table`) into `thresholds`, and each bucket's first
    // value into `buckets` from the first threshold's bucket (those under it kept).
    inline void thresholds_of(
        uint32_t table, int32_t* thresholds, tt_l1_ptr uint8_t* buckets
    ) {
        invalidate_l1_cache();
        const volatile tt_l1_ptr uint32_t* words = km::l1(table);
        for (uint32_t word = 0; word < kShowTableWords; ++word) {
            thresholds[word] = static_cast<int32_t>(words[word]);
        }
        const uint32_t above = static_cast<uint32_t>(thresholds[1]) - kShowBucketBase;
        const uint32_t from = above >> kShowBucketShift;
        for (uint32_t bucket = from, index = 0; bucket < kShowBuckets; ++bucket) {
            const int32_t start = (static_cast<int32_t>(
                kShowBucketBase + (bucket << kShowBucketShift)
            ));
            while (index < kShowTableWords - 1 && start >= thresholds[index + 1]) {
                ++index;
            }
            buckets[bucket] = static_cast<uint8_t>(index);
        }
    }

    // Rows [first_row, end_row) of the planes from `red` (green, blue after it) into
    // `pixels`, a page of 32 x 32 words.
    inline void colour_rows(
        const tt_l1_ptr uint32_t* red,
        tt_l1_ptr uint32_t* pixels,
        uint32_t first_row,
        uint32_t end_row,
        const int32_t* thresholds,
        const tt_l1_ptr uint8_t* buckets
    ) {
        const int32_t first = thresholds[1];
        const tt_l1_ptr uint32_t* green = red + kPlaneWords;
        const tt_l1_ptr uint32_t* blue = green + kPlaneWords;
        for (uint32_t row = first_row; row < end_row; ++row) {
            for (uint32_t column = 0; column < 32; ++column) {
                const uint32_t word = window_word(row, column);
                const uint32_t r = show_byte(thresholds, first, buckets, red[word]);
                const uint32_t g = show_byte(thresholds, first, buckets, green[word]);
                const uint32_t b = show_byte(thresholds, first, buckets, blue[word]);
                pixels[32 * row + column] = r | g << 8 | b << 16 | kShowAlpha;
            }
        }
    }

    // Rows [first_row, end_row) of one plane word for word, row-major into `pixels`.
    inline void plane_rows(
        const tt_l1_ptr uint32_t* plane,
        tt_l1_ptr uint32_t* pixels,
        uint32_t first_row,
        uint32_t end_row
    ) {
        for (uint32_t row = first_row; row < end_row; ++row) {
            for (uint32_t column = 0; column < 32; ++column) {
                pixels[32 * row + column] = plane[window_word(row, column)];
            }
        }
    }

}  // namespace show_k
