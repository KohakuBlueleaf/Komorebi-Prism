// FILL on the pack thread: the list's pages walked slot by slot, each item's tile
// filled on the vector unit and its planes pushed out; then the profile's words.
#pragma once

#include <stdint.h>

#include "out.hpp"
#include "triangle.hpp"

namespace fill_k {

    // One command's walk of a core's list, resumed at each of its pages.
    struct Walk {
        const km::Compute& compute;
        uint32_t out = 0;     // the items' planes, to the writer
        uint32_t across = 0;  // the grid's tiles a row (grid.h)
        fill::ProfileCounters counters;
        uint32_t started = 0, page_done = 0;
        uint32_t tile_x = 0, tile_y = 0, records_left = 0;
        int32_t first_row = 0, end_row = 32;
        bool listing = true, ended = false;

        explicit Walk(const km::Compute& compute) : compute(compute) {
        }

        // The command's start: the items' buffer, the grid's tiles a row, the unit set.
        void start(uint32_t planes, uint32_t grid) {
            out = planes;
            across = grid_of(grid).across;
            fill::setup();
            fill::edges(true);
            started = page_done = fill::wall();
        }

        // The item's planes out of Dst into the next kPlanes pages of `out`, pushed.
        bool tile_out() {
            uint32_t before = fill::wall();
            ckernel::tensix_sync();
            uint32_t after = fill::wall();
            counters.drain += after - before;
            if (!reserve_out(compute.control(), out, kPlanes)) {
                return false;
            }
            before = fill::wall();
            counters.wait_out += before - after;
            const uint32_t destination = out_ptr(out);
            if (!item_fits(compute.control(), out, destination, kPlanes)) {
                return false;
            }
            copy_band(destination, first_row, end_row);
            push_out(
                out,
                destination,
                (kPlanes - 1) * kPlaneWords + kRowBytes / 4 * end_row,
                kPlanes
            );
            counters.out += fill::wall() - before;
            counters.tiles++;
            return true;
        }

        // A tile's header: its tile, records and rows; false: a bad header (recorded).
        bool header(const volatile uint32_t* slot) {
            constexpr uint32_t background[3] = {0x3D4CCCCD, 0x3D4CCCCD, 0x3DA3D70A};
            const uint32_t tile = slot[kHdrTile];
            records_left = slot[kHdrCount];
            first_row = slot[kHdrRow0];
            end_row = slot[kHdrRow1];
            if (!(0 <= first_row && first_row < end_row && end_row <= 32 &&
                  tile < kTileCapacity)) {
                setup_k::give_up(compute.control(), kGaveBadItem, kWhereBadHeader);
                return false;
            }
            tile_x = tile % across;
            tile_y = tile / across;
            const uint32_t before = fill::wall();
            fill::init_tile(tile_x, tile_y, background);
            counters.init += fill::wall() - before;
            return records_left != 0 || tile_out();
        }

        // A record's rows in the item, on the vector unit.
        void record(const volatile uint32_t* record) {
            const uint32_t before = fill::wall();
            uint32_t record_words[kSlotWords];
#if defined(__riscv_vector)
            fill::copy_words_rvv(
                record_words, const_cast<const uint32_t*>(record), kSlotWords
            );
#else
            fill::fetch(record_words, record);
#endif
            const int32_t box_first_row =
                (static_cast<int32_t>(record_words[kRecY0]) - 32 * tile_y);
            const int32_t box_last_row =
                (static_cast<int32_t>(record_words[kRecY1]) - 32 * tile_y);
            const int32_t
                first_covered = (box_first_row < first_row ? first_row : box_first_row);
            const int32_t last_covered =
                (box_last_row > end_row - 1 ? end_row - 1 : box_last_row);
            fill::load_triangle(record_words);
            const uint32_t after = fill::wall();
            counters.triangle_setup += after - before;
            for (
                int32_t pixel_row = first_covered; pixel_row <= last_covered;
                ++pixel_row
            ) {
                fill::row(pixel_row);
                counters.row_count++;
            }
            counters.rows += fill::wall() - after;
            counters.triangles++;
        }

        // One list page (its L1 address), slot by slot, until the end slot.
        void page(uint32_t page_address) {
            asm volatile("fence" ::: "memory");
            counters.wait_in += fill::wall() - page_done;
            const volatile uint32_t*
                slots = (reinterpret_cast<const volatile uint32_t*>(page_address));
            for (uint32_t slot = 0; listing && slot < kSlotsPerPage; ++slot) {
                const volatile uint32_t* words = slots + kSlotWords * slot;
                if (records_left == 0) {  // a tile's header, or the end
                    if (words[0] == kMarkEnd) {
                        listing = false;
                        ended = true;
                    } else if (!header(words)) {
                        listing = false;
                    }
                    continue;
                }
                record(words);
                if (--records_left == 0 && !tile_out()) {
                    listing = false;
                }
            }
            page_done = fill::wall();
        }

        // The vector unit's state given back; the profile item (kPlanes pages): the
        // pack thread's counters at words 0 to 10, the others to word 31 zero.
        void end() {
            fill::finish();
            if (!ended) {  // a bad header or item, or the pages ended before the end
                           // slot
                if (listing) {
                    setup_k::give_up(compute.control(), kGaveWait, kWhereWaitPage);
                }
                return;
            }
            counters.total = fill::wall() - started;
            if (!reserve_out(compute.control(), out, kPlanes)) {
                return;
            }
            const uint32_t destination = out_ptr(out);
            if (!item_fits(compute.control(), out, destination, kPlanes)) {
                return;
            }
            volatile uint32_t* words = reinterpret_cast<volatile uint32_t*>(
                destination
            );
            const uint32_t values[11] = {
                counters.wait_in,
                counters.init,
                counters.triangle_setup,
                counters.rows,
                counters.drain,
                counters.out,
                counters.wait_out,
                counters.tiles,
                counters.triangles,
                counters.row_count,
                counters.total
            };
            for (uint32_t word = 0; word < 32; ++word) {
                words[word] = word < 11 ? values[word] : 0;
            }
            push_out(out, destination, 32, kPlanes);
        }
    };

}  // namespace fill_k
