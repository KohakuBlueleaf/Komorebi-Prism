// COUNT on mover B: per tile its entries and rows and the 2-row histograms (kept for
// HIST) from the pack thread's box words; the counters and costs sent.
#pragma once

#include <stdint.h>

#include "../common/space.hpp"

#include "../common/give_up.hpp"
#include "../common/profile.hpp"
#include "boxes.hpp"

namespace setup_k {

    // What COUNT's writer takes: the command's words and its buffers.
    struct CountWords {
        uint32_t counters_address;  // a tensor, a page of kCountBytes a core
        uint32_t heavy_bank;        // 1 + the heavy tiles' bank (RASTER_RECOUNT)
        uint32_t heavy_address;     // the heavy tiles' page, 0: a first COUNT
        uint32_t grid;              // the frame's grid (grid.h a8 bits 4 to 31)
        uint32_t out;               // the pack thread's pages
        uint32_t count;             // the command space (its counters part)
        uint32_t hist;              // the command space (its histograms part)
        uint32_t work;              // the pack thread's space
    };

    // COUNT's second stage: per tile entries and rows (the count buffer's space) and
    // the 2-row histograms (the hist buffer's, kept for HIST) from the box words.
    template <typename Writer>
    bool count_stage(
        const Writer& writer, const CountWords& words, WriterProfile& profile
    ) {
        const uint32_t control = writer.args().control;
        const uint32_t counters_address = words.counters_address;
        const uint32_t across = grid_of(words.grid).across;  // tile ty TX + tx
        // the frame's tiles in SUM's slices, not the capacity's
        const uint32_t tiles = slice_tiles(words.grid);
        const uint32_t out = words.out;
        // the counters, the histograms: their parts of the command space
        const uint32_t count = raster_space::counters(get_read_ptr(words.count));
        volatile tt_l1_ptr uint32_t* counters = km::l1(count);
        volatile tt_l1_ptr uint32_t* histogram_words = km::l1(
            raster_space::kept_hist(get_read_ptr(words.hist))
        );
        volatile tt_l1_ptr uint16_t*
            histogram = reinterpret_cast<volatile tt_l1_ptr uint16_t*>(histogram_words);
        const uint32_t zero_started = km::wall();
#ifdef RASTER_RECOUNT
        // COUNT counts (a4 0), or again its heavy tiles' histograms (a4 the heavy
        // tiles' page, README.md): through a map, 1 + heavy index a tile (count)
        const uint32_t heavy_address = words.heavy_address;
        volatile tt_l1_ptr uint16_t*
            heavy_of = reinterpret_cast<volatile tt_l1_ptr uint16_t*>(counters);
        if (heavy_address != 0) {
            const uint32_t heavy_space = count + 4 * kTiles;
            noc_async_read(
                noc_address(words.heavy_bank, heavy_address, 0, kHeavyBytes),
                heavy_space,
                kHeavyBytes
            );
            for (uint32_t i = 0; i < tiles / 2; ++i) {
                counters[i] = 0;
            }
            if (!arrived(writer)) {
                return false;
            }
            invalidate_l1_cache();
            volatile tt_l1_ptr uint32_t* heavy_words = km::l1(heavy_space);
            const uint32_t heavy_count = heavy_words[0];
            if (heavy_count > kHistTiles) {
                give_up(control, kGaveBadHeavy, heavy_count);
                return true;
            }
            for (uint32_t heavy_index = 0; heavy_index < heavy_count; ++heavy_index) {
                heavy_of[heavy_words[1 + heavy_index] % kTiles] = heavy_index + 1;
            }
            for (uint32_t i = 0; i < 16 * heavy_count; ++i) {
                histogram_words[i] = 0;
            }
        } else {
            for (uint32_t i = 0; i < tiles; ++i) {  // entries, then rows at kTiles
                counters[i] = counters[kTiles + i] = 0;
            }
        }
#else
        for (uint32_t i = 0; i < tiles; ++i) {  // entries, then rows at kTiles
            counters[i] = counters[kTiles + i] = 0;
        }
        for (uint32_t i = 0; i < 16 * tiles; ++i) {  // 64 bytes a tile
            histogram_words[i] = 0;
        }
#endif
        profile.write += km::wall() - zero_started;
        for (;;) {
            const uint32_t wait_start = km::wall();
            if (!writer.wait_front(out, 1, 4)) {
                return true;
            }
            const uint32_t wait_end = km::wall();
            profile.wait += wait_end - wait_start;
            invalidate_l1_cache();
            volatile tt_l1_ptr uint32_t* page_words = km::l1(get_read_ptr(out));
            const uint32_t head = page_words[0], box_words = head & ~kOutLast;
            ++profile.pages;
            for (
                uint32_t i = 0; i + kBoxWords <= box_words && i < kOutWords;
                i += kBoxWords
            ) {
                const BoxWord box = box_at(page_words + 1 + i);
                for (
                    uint32_t tile_y = box.first_row >> 5; tile_y <= box.last_row >> 5;
                    ++tile_y
                ) {
                    const uint32_t top = 32 * tile_y;
                    const uint32_t
                        first_row = (box.first_row > top ? box.first_row : top);
                    const uint32_t
                        last_row = (box.last_row < top + 31 ? box.last_row : top + 31);
                    for (
                        uint32_t tile_x = box.first_tile_x; tile_x <= box.last_tile_x;
                        ++tile_x
                    ) {
                        const uint32_t tile = across * tile_y + tile_x;
#ifdef RASTER_RECOUNT
                        if (heavy_address == 0) {
                            counters[tile] += 1;
                            counters[kTiles + tile] += last_row - first_row + 1;
                            continue;
                        }
                        const uint32_t heavy = heavy_of[tile];
                        if (heavy == 0) {
                            continue;
                        }
                        volatile tt_l1_ptr uint16_t*
                            tile_histogram = (histogram + 32 * (heavy - 1));
#else
                        counters[tile] += 1;
                        counters[kTiles + tile] += last_row - first_row + 1;
                        volatile tt_l1_ptr uint16_t*
                            tile_histogram = (histogram + 32 * tile);
#endif
                        const uint16_t
                            starts = (tile_histogram[(first_row - top) >> 1] + 1);
                        tile_histogram[(first_row - top) >> 1] = starts;
                        const uint16_t
                            ends = (tile_histogram[16 + ((last_row - top) >> 1)] + 1);
                        tile_histogram[16 + ((last_row - top) >> 1)] = ends;
                        if (starts == 0 || ends == 0) {
                            give_up(control, kGaveBadHist, tile);
                            cb_pop_front(out, 1);
                            return true;
                        }
                    }
                }
            }
            cb_pop_front(out, 1);
            profile.write += km::wall() - wait_end;
            if (head & kOutLast) {
                break;
            }
        }
#ifdef RASTER_RECOUNT
        if (heavy_address != 0) {  // the histograms stay for HIST; counters and costs
            return true;           // are the first COUNT's
        }
#endif
        const uint32_t send_started = km::wall();
        asm volatile("fence" ::
                         : "memory");  // the counters' stores land before the read
        // the frame's tiles' entries, and their rows at kTiles (SUM's slices)
        const uint64_t counters_page = (noc_address(
            0, counters_address, writer.me(), kCountBytes
        ));
        profile.bytes += 8 * tiles;
        noc_async_write(count, counters_page, 4 * tiles);
        noc_async_write(count + 4 * kTiles, counters_page + 4 * kTiles, 4 * tiles);
        const bool succeeded = flushed(writer);
        profile.write += km::wall() - send_started;
        return succeeded;
    }

}  // namespace setup_k
