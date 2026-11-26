// The kind `place` (answer.h TP_PLACE): the ranges a core counted, again, through the
// set-up pass; on the integer mover each record to its list at this core's running
// position of every tile or band it reaches. At a layer's first range the integer mover
// reads this core's positions page of the layer and the slices' places, and keeps the
// positions, made absolute, until the core leaves the layer.
#pragma once

#include <stdint.h>

#include "blocks.hpp"
#include "count.hpp"

namespace geometry_k {

#if !defined(COMPILE_FOR_TRISC)

    // The integer mover's state over a place pull: the layer whose positions it holds.
    struct PlaceHeld {
        uint32_t layer = kNoLayer;
    };

    inline PlaceHeld& place_held() {
        static PlaceHeld held;
        return held;
    }

    // Layer `layer`'s positions of this core into L1 (its tiles' words and its slices'
    // band entries) with every slice's place of the layer added. False: gave up.
    template <typename Ctx>
    bool place_load(Ctx& ctx, uint32_t layer) {
        km::Movement& movement = ctx.movement;
        const auto& page = ctx.frame;
        const Slices slices = slices_of(page);
        if (slices.count == 0) {
            return movement.gave_up_at(km::kGaveBadItem, kWhereSlice, __LINE__);
        }
        const uint32_t positions = layer_word(page, layer, TF_L_POSITIONS);
        const uint32_t at = get_write_ptr(Ctx::Buffers::geo_positions);
        const uint32_t places = get_write_ptr(Ctx::Buffers::geo_places);
        const uint32_t tile_bytes = 4 * kSliceTilesMost * slices.count;
        const uint32_t band_bytes = 4 * kBandWords * kSliceRecords * slices.count;
        noc_async_read(dram(0, positions, ctx.rank, kPositionBytes), at, tile_bytes);
        noc_async_read(
            dram(0, positions, ctx.rank, kPositionBytes, 4 * kPosTileWords),
            at + 4 * kPosTileWords,
            band_bytes
        );
        noc_async_read(
            dram(bank_word(page[TF_GRID]), page[TF_SLICES], 0, 0),
            places,
            kSliceBytes * slices.count
        );
        if (!landed(movement, kWherePositions)) {
            return false;
        }
        invalidate_l1_cache();
        volatile tt_l1_ptr uint32_t* words = km::l1(at);
        volatile tt_l1_ptr uint32_t* slice_words = km::l1(places);
        const uint32_t grid = grid_tiles(page[TF_GRID]);
        for (uint32_t tile = 0; tile < grid; ++tile) {
            const uint32_t place = slice_words
                [TS_WORDS * slice_of(slices, tile) + TS_PLACE(layer)];
            const uint32_t at_tile = tile_word(slices, tile);
            const uint32_t word = words[at_tile];
            if ((word & kPosCut) == 0) {
                words[at_tile] = word + place;
                continue;
            }
            const uint32_t first = word & kPosEntryMask;
            const uint32_t bands = word >> kPosBandsShift & kPosBandsMask;
            for (uint32_t entry = first; entry < first + bands; ++entry) {
                words[kPosTileWords + kBandWords * entry + 1] += place;
            }
        }
        return true;
    }

    // One range's pages from the pass: each record written to the next slot of every
    // tile or band of its layer its box reaches. False: gave up (recorded).
    template <typename Ctx>
    bool place_pages(Ctx& ctx, uint32_t layer) {
        km::Movement& movement = ctx.movement;
        constexpr uint32_t out = Ctx::Buffers::geo_out;
        const auto& page = ctx.frame;
        const uint32_t across = grid_of(page[TF_GRID]).across;
        const Slices slices = slices_of(page);
        volatile tt_l1_ptr uint32_t* positions = km::l1(
            get_write_ptr(Ctx::Buffers::geo_positions)
        );
        const InterleavedAddrGen<true> lists = {
            .bank_base_address = layer_word(page, layer, TF_L_LISTS),
            .page_size = setup_k::kListPageBytes
        };
        for (;;) {
            if (!front(movement, out, 1, kWhereOut)) {
                return false;
            }
            invalidate_l1_cache();
            const uint32_t records = get_read_ptr(out);
            volatile tt_l1_ptr uint32_t* words = km::l1(records);
            const uint32_t head = words[0];
            const uint32_t entries = head & ~setup_k::kOutLast;
            for (uint32_t i = 0; i < entries && i < setup_k::kOutEntries; ++i) {
                const uint32_t record = records + 4 * fill_k::kSlotWords * (1 + i);
#ifdef RASTER_WIDE
                const setup_k::BoxWord box = setup_k::record_box(km::l1(record));
#else
                const setup_k::BoxWord box = setup_k::box_at(words + 1 + i);
#endif
                for (
                    uint32_t tile_y = box.first_row >> 5; tile_y <= box.last_row >> 5;
                    ++tile_y
                ) {
                    const uint32_t top = kTileRows * tile_y;
                    const uint32_t first_group = ((box.first_row > top ? box.first_row
                                                                       : top) -
                                                  top) >>
                        1;
                    const uint32_t last_group = ((box.last_row < top + kTileRows - 1
                                                      ? box.last_row
                                                      : top + kTileRows - 1) -
                                                 top) >>
                        1;
                    for (
                        uint32_t tile_x = box.first_tile_x; tile_x <= box.last_tile_x;
                        ++tile_x
                    ) {
                        const uint32_t tile = across * tile_y + tile_x;
                        const uint32_t at_tile = tile_word(slices, tile);
                        const uint32_t word = positions[at_tile];
                        if ((word & kPosCut) == 0) {
                            positions[at_tile] = word + 1;
                            noc_async_write(
                                record,
                                get_noc_addr(
                                    word / fill_k::kSlotsPerPage,
                                    lists,
                                    (word % fill_k::kSlotsPerPage) * 128
                                ),
                                128
                            );
                            continue;
                        }
                        const uint32_t first = word & kPosEntryMask;
                        const uint32_t bands = word >> kPosBandsShift & kPosBandsMask;
                        for (uint32_t entry = first; entry < first + bands; ++entry) {
                            volatile tt_l1_ptr uint32_t* band = positions +
                                kPosTileWords + kBandWords * entry;
                            const uint32_t rows = band[0];
                            const uint32_t band_first = (rows & 0xFF) >> 1;
                            const uint32_t band_end = (rows >> kBandRowsEndShift) >> 1;
                            if (first_group >= band_end || last_group < band_first) {
                                continue;
                            }
                            const uint32_t slot = band[1];
                            band[1] = slot + 1;
                            noc_async_write(
                                record,
                                get_noc_addr(
                                    slot / fill_k::kSlotsPerPage,
                                    lists,
                                    (slot % fill_k::kSlotsPerPage) * 128
                                ),
                                128
                            );
                        }
                    }
                }
            }
            if (!sent(movement, kWhereListsSent)) {
                return false;
            }
            cb_pop_front(out, 1);
            if (head & setup_k::kOutLast) {
                return true;
            }
        }
    }

    // place on both movers, for the pull's range `range` (the ranges this core counted,
    // replayed): the streaming mover reads each unit's blocks (with their shade blocks
    // on a shaded layer); the integer mover places the records.
    template <typename Ctx, typename Range>
    bool place_movers(Ctx& ctx, const Range& range) {
        for (uint32_t unit = range.first; unit < range.first + range.count; ++unit) {
            const Span span = span_of(ctx.frame, unit);
            if (span.blocks == 0) {
                return ctx.movement.gave_up_at(km::kGaveBadItem, kWhereRange, __LINE__);
            }
            if constexpr (km::kMover == kStreamer) {
                if (!blocks_in<Ctx, true>(ctx, span, shaded(ctx.frame, span, true))) {
                    return false;
                }
            } else {
                PlaceHeld& held = place_held();
                if (span.layer != held.layer) {
                    if (held.layer != kNoLayer && span.layer < held.layer) {
                        return ctx.movement.gave_up_at(
                            km::kGaveBadItem, kWhereRange, __LINE__
                        );
                    }
                    if (!place_load(ctx, span.layer)) {
                        return false;
                    }
                    held.layer = span.layer;
                }
                if (!place_pages(ctx, span.layer)) {
                    return false;
                }
            }
        }
        return true;
    }

    // The place pull's end on both movers: no layer held (the lists are written).
    template <typename Ctx>
    bool place_end(Ctx& ctx) {
        static_cast<void>(ctx);
        place_held().layer = kNoLayer;
        return true;
    }

#else

    // place on the compute CPUs: each unit's blocks through the set-up pass (weighted
    // on a shaded layer), its records with their boxes to the integer mover.
    template <typename Ctx, typename Range>
    bool place_compute(Ctx& ctx, const Range& range) {
        for (uint32_t unit = range.first; unit < range.first + range.count; ++unit) {
            const Span span = span_of(ctx.frame, unit);
            if (span.blocks == 0) {
                ctx.compute.gave_up(km::kGaveBadItem, kWhereRange);
                return false;
            }
            const bool with_shade = shaded(ctx.frame, span, true);
            if (!pass_over<Ctx, true>(ctx, span, setup_k::kHandlerSetup, with_shade)) {
                return false;
            }
        }
        return true;
    }

    // The place pull's end on the compute CPUs: nothing is held.
    template <typename Ctx>
    bool place_end(Ctx& ctx) {
        static_cast<void>(ctx);
        return true;
    }

#endif

}  // namespace geometry_k
