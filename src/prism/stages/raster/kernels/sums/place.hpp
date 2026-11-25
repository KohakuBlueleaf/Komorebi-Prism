// PLACE on mover B: from the items region's two ranges (the items table; the frame,
// item and core words), this core's directory page and end slot, and its headers.
#pragma once

#include <stdint.h>

#include "../common/give_up.hpp"
#include "../common/layouts.hpp"
#include "../common/noc.hpp"

namespace setup_k {

    // What PLACE takes: the region's ranges in L1 and the command's words.
    struct PlaceWords {
        uint32_t low;            // the region from its first page (the items table)
        uint32_t high;           // the region from page `high_page`
        uint32_t high_page;      // the high range's first page
        uint32_t tiles;          // scratch: each item's tile (uint16)
        uint32_t page;           // this core's directory page, put after
        uint32_t slots;          // its end slot, then 32 headers at a time
        uint32_t fill_cores;     // the cores that fill
        uint32_t lists_address;  // the lists (pages of kListPageBytes)
        uint32_t grid;           // the frame's grid (grid.h a8 bits 4 to 31)
    };

    // -1: go on (the directory page and end slot made, the headers sent); else the
    // command's result after a give-up (1) or a NoC wait that gave up (0).
    template <typename Writer>
    int place(
        const Writer& writer,
        const PlaceWords& words,
        uint32_t cores,
        uint32_t& end_slot
    ) {
        const uint32_t control = writer.args().control, fill_cores = words.fill_cores;
        // the frame's tiles, not the capacity's
        const uint32_t tiles = grid_tiles(words.grid);
        const uint32_t high = words.high - 4096 * words.high_page;
        volatile tt_l1_ptr uint32_t* items = km::l1(words.low);
        const volatile tt_l1_ptr uint16_t*
            rows = (reinterpret_cast<volatile tt_l1_ptr uint16_t*>(
                words.low + kItemRows
            ));
        volatile tt_l1_ptr uint32_t* item_words = km::l1(high + kItemWordsAt);
        volatile tt_l1_ptr uint32_t* core_words = km::l1(high + kCoreWordsAt);
        volatile tt_l1_ptr uint32_t* frame_words = km::l1(high + kFrameWordsAt);
        volatile tt_l1_ptr uint16_t*
            tile_of = (reinterpret_cast<volatile tt_l1_ptr uint16_t*>(words.tiles));
        uint32_t item_count = 0;
        for (uint32_t tile = 0; tile < tiles; ++tile) {
            const uint32_t first = items[tile] & 0xFFFF;
            const uint32_t items_in_tile = items[tile] >> 16;
            for (
                uint32_t i = first; i < first + items_in_tile && i < kSlotsBytes / 4;
                ++i
            ) {
                tile_of[i] = tile;
            }
            item_count = first + items_in_tile;
        }
        if (item_count > kSlotsBytes / 4 || fill_cores > kMaxFillCores) {
            give_up(control, kGaveBadPlace, 1);
            return 1;
        }
        const InterleavedAddrGen<true> lists = {
            .bank_base_address = words.lists_address, .page_size = kListPageBytes
        };
        const uint32_t me = writer.me();
        auto build_slot = [&](uint32_t slot_address, uint32_t mark, uint32_t i) {
            volatile tt_l1_ptr uint32_t* slot_words = km::l1(slot_address);
            for (uint32_t word = 0; word < 32; ++word) {
                slot_words[word] = 0;
            }
            slot_words[0] = mark;
            if (mark == kLayMarkTile) {
                slot_words[kLayHdrTile] = tile_of[i];
                slot_words[kLayHdrCount] = item_words[kItemWords * i] >> 8;
                slot_words[kLayHdrRow0] = rows[i] & 0xFF;
                slot_words[kLayHdrRow1] = rows[i] >> 8;
            }
        };
        if (me < fill_cores) {
            volatile tt_l1_ptr uint32_t* directory = km::l1(words.page);
            for (uint32_t word = 0; word < kDirPageBytes / 4; ++word) {
                directory[word] = 0;
            }
            uint32_t directory_items = 0;
            for (
                uint32_t i = 0;
                i < item_count && directory_items < kLayDirFrame - kLayDirIds;
                ++i
            ) {
                const uint32_t item_word = item_words[kItemWords * i];
                if ((item_word & 0xFF) != me) {
                    continue;
                }
                uint32_t id = tile_of[i];
                if (rows[i] != (32u << 8)) {
                    id |=
                        ((rows[i] & 0xFF) << kLayRow0Shift |
                         (rows[i] >> 8) << kLayRow1Shift);
                }
                directory[kLayDirIds + directory_items++] =
                    ((item_word >> 8) == 0 ? id | kLayItemEmpty : id);
            }
            directory[0] = core_words[kCoreWords * me];
            directory[1] = core_words[kCoreWords * me + 1];
            directory[2] = directory_items;
            for (uint32_t word = 0; word < 16; ++word) {
                directory[kLayDirFrame + word] = frame_words[word];
            }
            end_slot = core_words[kCoreWords * me + 3];
            build_slot(words.slots, kLayMarkEnd, 0);
            asm volatile("fence" ::: "memory");  // the pages' stores before the puts
        }
        // headers, 32 at a time
        uint32_t batched = 0;
        const uint32_t header_space = words.slots + kOutBytes;
        for (uint32_t i = me; i < item_count; i += cores) {
            if ((item_words[kItemWords * i] >> 8) == 0) {
                continue;
            }
            const uint32_t slot_address = header_space + 128 * batched;
            const uint32_t slot = item_words[kItemWords * i + 1];
            build_slot(slot_address, kLayMarkTile, i);
            asm volatile("fence" ::: "memory");
            noc_async_write(
                slot_address, get_noc_addr(slot / 16, lists, (slot % 16) * 128), 128
            );
            if (++batched == kOutBytes / 128) {
                if (!flushed(writer)) {
                    return 0;
                }
                batched = 0;
            }
        }
        return flushed(writer) ? -1 : 0;
    }

}  // namespace setup_k
