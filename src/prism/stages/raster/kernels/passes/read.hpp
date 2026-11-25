// SETUP on mover A: the slots and items pages (or the slots made from SUM's and
// HSUM's prefixes), before the lines read the camera's page and the mesh blocks.
#pragma once

#include <stdint.h>

#include "../common/space.hpp"

#include "../common/layouts.hpp"
#include "../common/noc.hpp"
#include "api/dataflow/dataflow_api.h"
#include "komorebi/device/km_worker.hpp"

namespace setup_k {

    // What SETUP's reader takes besides the slot words: the regions' bank, the grid.
    struct ReadWords {
        uint32_t bank;  // 1 + the regions' DRAM bank
        uint32_t grid;  // the frame's grid (the view's word)
    };

    // SETUP's further words: the slots and items pages and their buffers.
    struct SlotWords {
        uint32_t slots_address;  // a tensor, a page of kSlotsBytes a core
        uint32_t list_slots;     // the lists' slots, kSetupPrefix
        uint32_t items_address;  // the items region in the bank
        uint32_t slots;          // the slots buffer, to the writer
        uint32_t items;          // the items buffer, to the writer
        uint32_t space;          // the command space (its kept_hist part: the prefixes)
    };

    // kSetupPrefix: base + SUM's entries before (a whole tile) or HSUM's starts before
    // end_row less ends before first_row (README.md); in place, tiles from the last.
    template <typename Reader>
    bool slots_from_prefixes(
        const Reader& reader, const ReadWords& words, const SlotWords& slot_words
    ) {
        const uint32_t items_address = slot_words.items_address, bank = words.bank;
        // the frame's tiles, not the capacity's
        const uint32_t tiles = grid_tiles(words.grid);
        const uint32_t space = raster_space::kept_hist(get_write_ptr(slot_words.space));
        constexpr uint32_t kRead = kHprefixAddrAt - kBaseAt +
            64;  // base words, address
        // the frame's items' base words, then the address (each on 64 bytes)
        static_assert(kBaseAt % 64 == 0 && kHprefixAddrAt % 64 == 0);
        noc_async_read(
            noc_address(bank, items_address, 0, 0, kBaseAt),
            space,
            (4 * (tiles + kBandItems) + 63) & ~63u
        );
        noc_async_read(
            noc_address(bank, items_address, 0, 0, kHprefixAddrAt),
            space + (kHprefixAddrAt - kBaseAt),
            64
        );
        if (!arrived(reader)) {
            return false;
        }
        invalidate_l1_cache();
        volatile tt_l1_ptr uint32_t* items = km::l1(get_write_ptr(slot_words.items));
        volatile tt_l1_ptr uint32_t* base_words = km::l1(space);
        const uint32_t last = items[tiles - 1];  // tiles past the grid: none
        const uint32_t item_count = (last & 0xFFFF) + (last >> 16);
        if (item_count > kSlotsBytes / 4) {
            return false;
        }
        uint32_t heavy_tiles = 0;
        for (uint32_t item = 0; item < item_count; ++item) {
            const uint32_t heavy_index = base_words[item] >> kBaseSlotBits;
            heavy_tiles = heavy_index > heavy_tiles ? heavy_index : heavy_tiles;
        }
        const uint32_t counts = space + kRead;
        const uint32_t
            prefix_pages_address = (base_words[(kHprefixAddrAt - kBaseAt) / 4]);
        if (heavy_tiles > kHprefixPageBytes / 128) {
            return false;
        }
        if (heavy_tiles != 0) {
            noc_async_read(
                noc_address(0, prefix_pages_address, reader.me(), kHprefixPageBytes),
                counts,
                128 * heavy_tiles
            );
            if (!arrived(reader)) {
                return false;
            }
            invalidate_l1_cache();
        }
        volatile tt_l1_ptr uint32_t* slots = km::l1(get_write_ptr(slot_words.slots));
        const volatile tt_l1_ptr uint16_t*
            rows = (reinterpret_cast<volatile tt_l1_ptr uint16_t*>(
                get_write_ptr(slot_words.items) + kItemRows
            ));
        constexpr uint32_t kSlotMask = (1u << kBaseSlotBits) - 1;
        for (uint32_t tile = tiles; tile-- > 0;) {
            const uint32_t first = items[tile] & 0xFFFF;
            const uint32_t items_in_tile = items[tile] >> 16;
            const uint32_t before = slots[tile];
            for (
                uint32_t item = first;
                item < first + items_in_tile && item < item_count;
                ++item
            ) {
                const uint32_t base_word = base_words[item];
                const uint32_t heavy_index = base_word >> kBaseSlotBits;
                uint32_t next_slot = base_word & kSlotMask;
                if (heavy_index == 0) {
                    next_slot += before;
                } else {
                    volatile tt_l1_ptr uint32_t* prefix_counts = (km::l1(
                        counts + 128 * (heavy_index - 1)
                    ));
                    const uint32_t end_group = (rows[item] >> 8) >> 1;
                    const uint32_t start_group = (rows[item] & 0xFF) >> 1;
                    next_slot +=
                        ((end_group ? prefix_counts[end_group - 1] : 0) -
                         (start_group ? prefix_counts[16 + start_group - 1] : 0));
                }
                slots[item] = next_slot;
            }
        }
        asm volatile("fence" ::: "memory");  // the stores land before the push
        return true;
    }

    // SETUP's slots and items pages: the frame's tiles' and items' words alone (each
    // part on 64 bytes), or the slots from the prefixes; pushed to the writer.
    template <typename Reader>
    bool read_slots(
        const Reader& reader, const ReadWords& words, const SlotWords& slot_words
    ) {
        if (!reader.reserve(slot_words.slots, 1) ||
            !reader.reserve(slot_words.items, 1)) {
            return false;
        }
        const uint32_t tiles = grid_tiles(words.grid);
        const uint32_t item_bytes = 4 * (tiles + kBandItems);
        static_assert(kItemRows % 64 == 0);
        noc_async_read(
            noc_address(0, slot_words.slots_address, reader.me(), kSlotsBytes),
            get_write_ptr(slot_words.slots),
            (item_bytes + 63) & ~63u
        );
        noc_async_read(
            noc_address(words.bank, slot_words.items_address, 0, kItemsBytes),
            get_write_ptr(slot_words.items),
            (4 * tiles + 63) & ~63u
        );
        noc_async_read(
            noc_address(
                words.bank, slot_words.items_address, 0, kItemsBytes, kItemRows
            ),
            get_write_ptr(slot_words.items) + kItemRows,
            (item_bytes / 2 + 63) & ~63u
        );
        if (!arrived(reader)) {
            return false;
        }
        if ((slot_words.list_slots & kSetupPrefix) != 0 &&
            !slots_from_prefixes(reader, words, slot_words)) {
            return false;
        }
        cb_push_back(slot_words.slots, 1);
        cb_push_back(slot_words.items, 1);
        return true;
    }

}  // namespace setup_k
