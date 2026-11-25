// Lit SHADE on the pack thread: an item's winners (each pixel's triangle) as slots of
// the lit space, open addressing on the triangle's bits, and each pixel's slot offset.
#pragma once

#include <stdint.h>

#include "../../../../../direct/light/kernels/light.h"
#include "../vector.hpp"

namespace shade_k {

    using light_k::kLitSlotEmpty;
    using light_k::kLitSlotWords;
    using light_k::kLwHashSize;

    constexpr uint32_t
        kSlotUnfilled = 0xFFFFFFFF;  // a slot's material word until filled

    // The winners of an item: triangle bits -> slot, open addressing (kLwHashSize).
    struct Winners {
        uint32_t* keys;
        uint32_t* slots;
        uint32_t* words;  // kLitSlotWords a slot, the empty pixels' at kLitSlotEmpty
        uint32_t count = 0;

        void clear(size_t vl) {
            const vuint32m8_t zero = __riscv_vmv_v_x_u32m8(0, vl);
            for (uint32_t i = 0; i < kLwHashSize; i += 32) {
                __riscv_vse32_v_u32m8(keys + i, zero, vl);
            }
            asm volatile("" ::: "memory");
            count = 0;
        }

        // The slot of triangle `bits` (insert: a new one, unfilled); kLitSlotEmpty when
        // not found.
        uint32_t find(uint32_t bits, bool insert) {
            const uint32_t key = bits + 1;
            uint32_t place = (key * 2654435761u) >> 21;
            for (;;) {
                const uint32_t held = keys[place];
                if (held == key) {
                    return slots[place];
                }
                if (held == 0) {
                    if (!insert || count == kLitSlotEmpty) {
                        return kLitSlotEmpty;
                    }
                    keys[place] = key;
                    slots[place] = count;
                    words[kLitSlotWords * count] = kSlotUnfilled;
                    return count++;
                }
                place = (place + 1) & (kLwHashSize - 1);
            }
        }
    };

    // Rows [first_row, end_row): each pixel's slot (its triangle's; the empty pixels'
    // slot) as a byte offset in `slot_offsets`, the rows' triangles through `row_bits`.
    inline void item_winners(
        Winners& winners,
        int32_t first_row,
        int32_t end_row,
        uint32_t* row_bits,
        uint32_t* slot_offsets,
        size_t vl
    ) {
        winners.clear(vl);
        uint32_t last_bits = 0xFFFFFFFF, last_slot = kLitSlotEmpty;
        for (int32_t r = first_row; r < end_row; ++r) {
            __riscv_vse32_v_u32m8(
                row_bits, texel_pages::from_window(kVecTri + r, vl), vl
            );
            asm volatile("" ::: "memory");
            for (uint32_t column = 0; column < 32; ++column) {
                const uint32_t bits = row_bits[column];
                if (bits != last_bits) {
                    last_bits = bits;
                    last_slot = bits >> 31 ? kLitSlotEmpty : winners.find(bits, true);
                }
                slot_offsets[32 * r + column] = 4 * kLitSlotWords * last_slot;
            }
        }
    }

}  // namespace shade_k
