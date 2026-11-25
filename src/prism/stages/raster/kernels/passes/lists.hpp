// SETUP on mover B: each record of the pack thread's pages to the next slot of every
// item (a tile, or a band of its rows) its box reaches.
#pragma once

#include <stdint.h>

#include "../common/give_up.hpp"
#include "../common/profile.hpp"
#include "boxes.hpp"

namespace setup_k {

    // What SETUP's writer takes: the command's words and its buffers.
    struct ListWords {
        uint32_t lists_address;  // the lists (pages of kListPageBytes)
        uint32_t list_slots;     // the lists' slots, kSetupPrefix
        uint32_t grid;           // the frame's grid (the view's word)
        uint32_t out;            // the pack thread's pages
        uint32_t slots;          // the next slots page, from the reader
        uint32_t items;          // the items page, from the reader
    };

    // SETUP's second stage: each record of the pack thread's pages to the next slot of
    // every item (a tile, or a band of its rows) its box reaches.
    template <typename Writer>
    [[gnu::noinline]] bool setup_stage(
        const Writer& writer, const ListWords& words, WriterProfile& profile
    ) {
        const uint32_t control = writer.args().control;
        const uint32_t lists_address = words.lists_address, out = words.out;
        const uint32_t list_slots = words.list_slots & ~kSetupPrefix;
        const uint32_t across = grid_of(words.grid).across;  // tile ty TX + tx
        if (!writer.wait_front(words.slots, 1, 4) ||
            !writer.wait_front(words.items, 1, 4)) {
            return true;
        }
        invalidate_l1_cache();
        volatile tt_l1_ptr uint32_t* next_slot = km::l1(get_read_ptr(words.slots));
        volatile tt_l1_ptr uint32_t* items = km::l1(get_read_ptr(words.items));
        const volatile tt_l1_ptr uint16_t*
            rows = (reinterpret_cast<const volatile tt_l1_ptr uint16_t*>(
                get_read_ptr(words.items) + kItemRows
            ));
        const InterleavedAddrGen<true> lists = {
            .bank_base_address = lists_address, .page_size = kListPageBytes
        };
        bool succeeded = true;
        for (;;) {
            const uint32_t wait_start = km::wall();
            if (!writer.wait_front(out, 1, 4)) {
                return true;
            }
            const uint32_t wait_end = km::wall();
            profile.wait += wait_end - wait_start;
            invalidate_l1_cache();
            const uint32_t page = get_read_ptr(out);
            volatile tt_l1_ptr uint32_t* page_words = km::l1(page);
            const uint32_t head = page_words[0], entries = head & ~kOutLast;
            ++profile.pages;
            for (uint32_t i = 0; i < entries && i < kOutEntries && succeeded; ++i) {
#ifdef RASTER_WIDE
                const BoxWord box = record_box(page_words + 32 * (1 + i));
#else
                const BoxWord box = box_at(page_words + 1 + i);
#endif
                for (
                    uint32_t tile_y = box.first_row >> 5;
                    tile_y <= box.last_row >> 5 && succeeded;
                    ++tile_y
                ) {
                    const uint32_t top = 32 * tile_y;
                    const uint32_t
                        first_row = (box.first_row > top ? box.first_row : top);
                    const uint32_t
                        last_row = (box.last_row < top + 31 ? box.last_row : top + 31);
                    for (
                        uint32_t tile_x = box.first_tile_x;
                        tile_x <= box.last_tile_x && succeeded;
                        ++tile_x
                    ) {
                        const uint32_t tile = across * tile_y + tile_x;
                        const uint32_t first = items[tile] & 0xFFFF;
                        const uint32_t item_count = items[tile] >> 16;
                        if (first + item_count > kSlotsBytes / 4) {
                            give_up(control, kGaveBadSlot, tile);
                            succeeded = false;
                            break;
                        }
                        for (uint32_t item = first; item < first + item_count; ++item) {
                            // the item's rows [item_first_row, item_end_row) against
                            // the entry's 2-row groups
                            const uint32_t item_first_row = rows[item] & 0xFF;
                            const uint32_t item_end_row = rows[item] >> 8;
                            if (((first_row - top) >> 1) >= (item_end_row >> 1) ||
                                ((last_row - top) >> 1) < (item_first_row >> 1)) {
                                continue;
                            }
                            const uint32_t entry_slot = next_slot[item];
                            next_slot[item] = entry_slot + 1;
                            if (entry_slot >= list_slots) {
                                give_up(control, kGaveBadSlot, tile);
                                succeeded = false;
                                break;
                            }
                            noc_async_write(
                                page + 128 * (1 + i),
                                get_noc_addr(
                                    entry_slot / 16, lists, (entry_slot % 16) * 128
                                ),
                                128
                            );
                            profile.bytes += 128;
                        }
                    }
                }
            }
            succeeded = flushed(writer) && succeeded;
            cb_pop_front(out, 1);
            profile.write += km::wall() - wait_end;
            if (!succeeded) {
                return false;
            }
            if (head & kOutLast) {
                break;
            }
        }
        cb_pop_front(words.slots, 1);
        cb_pop_front(words.items, 1);
        return true;
    }

}  // namespace setup_k
