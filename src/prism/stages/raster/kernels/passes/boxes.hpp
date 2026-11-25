// COUNT's and SETUP's writer: a kept triangle's box as the pack thread hands it,
// narrow (one word) or wide (grid.h: three words, or the record's box words).
#pragma once

#include <stdint.h>

#include "../common/layouts.hpp"
#include "komorebi/device/km_worker.hpp"

namespace setup_k {

    // A kept triangle's tile columns and pixel rows, as the pack thread hands them.
    struct BoxWord {
        uint32_t first_tile_x, last_tile_x, first_row, last_row;
    };

#ifdef RASTER_WIDE
    // Wide (grid.h): COUNT's box in three words, tile columns 16 bits each, then the
    // first and the last pixel row; SETUP's from its record's box words.
    constexpr uint32_t kBoxWords = 3;

    inline BoxWord box_at(const volatile tt_l1_ptr uint32_t* words) {
        return {words[0] & 0xFFFF, words[0] >> 16, words[1], words[2]};
    }

    // The integer n in [0, 2^24) whose float32 bits are `bits` (a wide record's box
    // column).
    inline uint32_t integer_of(uint32_t bits) {
        if (bits == 0) {
            return 0;
        }
        const uint32_t exponent = (bits >> 23) - 127;
        return ((bits & 0x7FFFFF) | 0x800000) >> (23 - exponent);
    }

    // A record's box (raster.h kRecX0 to kRecY1: first column and last + 1 as float32,
    // first and last row).
    inline BoxWord record_box(const volatile tt_l1_ptr uint32_t* record) {
        return {
            integer_of(record[kRawX0]) >> 5,
            (integer_of(record[kRawX1]) - 1) >> 5,
            record[kRawY0],
            record[kRawY1]
        };
    }
#else
    // Narrow: one word, tile columns in 6 bits each, pixel rows in 10.
    constexpr uint32_t kBoxWords = 1;

    inline BoxWord box_at(const volatile tt_l1_ptr uint32_t* words) {
        const uint32_t word = words[0];
        return {word & 63, word >> 6 & 63, word >> 12 & 1023, word >> 22 & 1023};
    }
#endif
    static_assert(kOutWords % kBoxWords == 0);  // a COUNT page holds whole boxes

}  // namespace setup_k
