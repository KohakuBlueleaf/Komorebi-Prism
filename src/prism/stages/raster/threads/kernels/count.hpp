// The kind `count` (answer.h TP_COUNT): a range of a layer's triangle blocks through
// the projection pass; on the integer mover each kept box into this core's entries by
// tile and its row histograms, kept in L1 across the ranges of the layer and written
// to its pages of the layer when the core leaves it; at the pull's end, the layer held
// and zeros for every layer the core took nothing of.
#pragma once

#include <stdint.h>

#include "blocks.hpp"
#if !defined(COMPILE_FOR_TRISC)
#include "../../kernels/passes/boxes.hpp"
#endif

namespace geometry_k {

    // No layer held (a pull's start).
    inline constexpr uint32_t kNoLayer = 0xFFFFFFFFu;

#if !defined(COMPILE_FOR_TRISC)

    // The integer mover's state over a count pull: the layer whose counts are in L1.
    struct CountHeld {
        uint32_t layer = kNoLayer;
    };

    inline CountHeld& count_held() {
        static CountHeld held;
        return held;
    }

    // The frame's tiles rounded up to whole 64-byte lines of the counts page.
    template <typename Words>
    inline uint32_t counted_tiles(const Words& page) {
        const uint32_t tiles = grid_tiles(page[TF_GRID]);
        return (tiles + kLine / kCountTileBytes - 1) & ~(kLine / kCountTileBytes - 1);
    }

    // The counts and histograms in L1 zeroed (the frame's tiles).
    template <typename Ctx>
    void count_zero(Ctx& ctx) {
        const uint32_t tiles = counted_tiles(ctx.page);
        volatile tt_l1_ptr uint32_t* counts = km::l1(
            ctx.kept(prism_frame::kKeptCountCounts)
        );
        volatile tt_l1_ptr uint32_t* rows = km::l1(
            ctx.kept(prism_frame::kKeptCountRows)
        );
        for (uint32_t i = 0; i < tiles; ++i) {
            counts[i] = 0;
        }
        for (uint32_t i = 0; i < tiles * kHistTileBytes / 4; ++i) {
            rows[i] = 0;
        }
    }

    // The L1 counts written as layer `layer`'s: this core's counts page and row
    // histograms page of it. False: gave up (recorded).
    template <typename Ctx>
    bool count_send(Ctx& ctx, uint32_t layer) {
        const auto& page = ctx.page;
        const uint32_t counts = layer_word(page, layer, TF_L_COUNTS);
        const uint32_t rows = layer_word(page, layer, TF_L_ROWS);
        if (counts == 0 || rows == 0) {
            return true;
        }
        const uint32_t tiles = counted_tiles(page);
        asm volatile("fence" ::: "memory");  // the counts' stores before the reads
        noc_async_write(
            ctx.kept(prism_frame::kKeptCountCounts),
            dram(0, counts, ctx.rank, kCountBytes),
            kCountTileBytes * tiles
        );
        noc_async_write(
            ctx.kept(prism_frame::kKeptCountRows),
            dram(0, rows, ctx.rank, kHistBytes),
            kHistTileBytes * tiles
        );
        prism_frame::account_add(
            ctx, FX_BYTES_PAGES, (kCountTileBytes + kHistTileBytes) * tiles
        );
        return sent(ctx.movement, kWhereCountsSent);
    }

    // The core moves to layer `next` (the page's layers: the pull's end): the layer
    // held written, zeros written for each layer between, the counts zeroed. False:
    // gave up (recorded), also for a layer before the one held.
    template <typename Ctx>
    bool count_move(Ctx& ctx, uint32_t next) {
        CountHeld& held = count_held();
        const uint32_t layers = layers_of(ctx.page);
        uint32_t zero_from = 0;
        if (held.layer != kNoLayer) {
            if (next < held.layer) {
                return ctx.gave_up(km::kGaveBadItem, kWhereRange);
            }
            if (!count_send(ctx, held.layer)) {
                return false;
            }
            zero_from = held.layer + 1;
        }
        count_zero(ctx);
        for (uint32_t layer = zero_from; layer < next && layer < layers; ++layer) {
            if (!count_send(ctx, layer)) {
                return false;
            }
        }
        held.layer = next < layers ? next : kNoLayer;
        return true;
    }

    // One range's pages from the pass: each kept box into the entries of every tile it
    // reaches and that tile's histograms of starts and ends by 2-row group. False:
    // gave up (recorded).
    template <typename Ctx>
    bool count_pages(Ctx& ctx) {
        km::Movement& movement = ctx.movement;
        constexpr uint32_t out = Ctx::Buffers::out;
        const uint32_t across = grid_of(ctx.page[TF_GRID]).across;
        volatile tt_l1_ptr uint32_t* counts = km::l1(
            ctx.kept(prism_frame::kKeptCountCounts)
        );
        volatile tt_l1_ptr uint16_t*
            histogram = reinterpret_cast<volatile tt_l1_ptr uint16_t*>(
                ctx.kept(prism_frame::kKeptCountRows)
            );
        for (;;) {
            if (!front(movement, out, 1, kWhereOut)) {
                return false;
            }
            invalidate_l1_cache();
            volatile tt_l1_ptr uint32_t* words = km::l1(get_read_ptr(out));
            const uint32_t head = words[0];
            const uint32_t box_words = head & ~setup_k::kOutLast;
            for (
                uint32_t i = 0;
                i + setup_k::kBoxWords <= box_words && i < setup_k::kOutWords;
                i += setup_k::kBoxWords
            ) {
                const setup_k::BoxWord box = setup_k::box_at(words + 1 + i);
                for (
                    uint32_t tile_y = box.first_row >> 5; tile_y <= box.last_row >> 5;
                    ++tile_y
                ) {
                    const uint32_t top = kTileRows * tile_y;
                    const uint32_t first_row = box.first_row > top ? box.first_row
                                                                   : top;
                    const uint32_t last_row = box.last_row < top + kTileRows - 1
                        ? box.last_row
                        : top + kTileRows - 1;
                    for (
                        uint32_t tile_x = box.first_tile_x; tile_x <= box.last_tile_x;
                        ++tile_x
                    ) {
                        const uint32_t tile = across * tile_y + tile_x;
                        counts[tile] += 1;
                        volatile tt_l1_ptr uint16_t* tile_histogram = histogram +
                            kHistTileBytes / 2 * tile;
                        const uint16_t starts = tile_histogram[(first_row - top) >> 1] +
                            1;
                        tile_histogram[(first_row - top) >> 1] = starts;
                        const uint16_t
                            ends = tile_histogram[kGroups + ((last_row - top) >> 1)] +
                            1;
                        tile_histogram[kGroups + ((last_row - top) >> 1)] = ends;
                        if (starts == 0 || ends == 0) {
                            cb_pop_front(out, 1);
                            return ctx.gave_up(km::kGaveBadItem, kWhereHist);
                        }
                    }
                }
            }
            cb_pop_front(out, 1);
            if (head & setup_k::kOutLast) {
                return true;
            }
        }
    }

#endif

}  // namespace geometry_k

#if !defined(COMPILE_FOR_TRISC)

// count on both movers, for the pull's range `range` (one layer's blocks): the
// streaming mover reads its blocks; the integer mover counts them. False: gave up
// (recorded).
template <typename Ctx>
bool count_movers(Ctx& ctx, const prism_frame::Range& range) {
    using namespace geometry_k;
    if (!range_fits(ctx.page, range)) {
        return ctx.gave_up(km::kGaveBadItem, kWhereRange);
    }
    if constexpr (km::kMover == kStreamer) {
        return blocks_in<Ctx, false>(ctx, range, false);
    } else {
        if (range.layer != count_held().layer && !count_move(ctx, range.layer)) {
            return false;
        }
        return count_pages(ctx);
    }
}

// The count pull's end on both movers (every core of the group, ranges or none): on
// the integer mover the layer held written and zeros for every layer after it.
template <typename Ctx>
bool count_end(Ctx& ctx) {
    using namespace geometry_k;
    if constexpr (km::kMover == kStreamer) {
        static_cast<void>(ctx);
        return true;
    } else {
        return count_move(ctx, layers_of(ctx.page));
    }
}

#else

// count on the compute CPUs: the range's blocks through the projection pass, its box
// words to the integer mover. False: gave up (recorded).
template <typename Ctx>
bool count_compute(Ctx& ctx, const prism_frame::Range& range) {
    using namespace geometry_k;
    if (!range_fits(ctx.page, range)) {
        ctx.compute.gave_up(km::kGaveBadItem, kWhereRange);
        return false;
    }
    return pass_over<Ctx, false>(ctx, range, setup_k::kHandlerCount, false);
}

// The count pull's end on the compute CPUs: nothing is held.
template <typename Ctx>
bool count_end(Ctx& ctx) {
    static_cast<void>(ctx);
    return true;
}

#endif
