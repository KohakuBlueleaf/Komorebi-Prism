// The sums as the hand kernel of an ordinary command (sums.py): each core takes the
// slices of its rank (slice s to rank s mod cores), its two movers the turns in turn.
// For a slice: every core's counts of its tiles summed by layer; a tile heavier than
// the page's TF_HEAVY cut into bands from every core's row histograms; the slice's
// records in order of weight, its words, and each core's first positions.
#pragma once

#include <stdint.h>

#include "reads.hpp"

namespace geometry_k {

    // Every layer's counts of the slice's run summed over the cores. False: gave up.
    template <typename Core>
    bool slice_totals(
        const Core& core, const SumView& view, SumScratch& scratch, SliceTiles run
    ) {
        for (uint32_t layer = 0; layer < TR_LAYERS; ++layer) {
            for (uint32_t column = 0; column < kSliceTilesMost; ++column) {
                scratch.totals[layer][column] = 0;
            }
        }
        for (uint32_t layer = 0; layer < view.layers; ++layer) {
            for (uint32_t first = 0; first < view.cores; first += kSumCores) {
                const uint32_t left = view.cores - first;
                const uint32_t cores = left < kSumCores ? left : kSumCores;
                if (!read_counts(core, view, scratch, layer, run, first, cores)) {
                    return false;
                }
                for (uint32_t c = 0; c < cores; ++c) {
                    for (uint32_t column = 0; column < run.count; ++column) {
                        scratch.totals[layer][column] += count_at(
                            scratch, run, c, column
                        );
                    }
                }
            }
        }
        for (uint32_t column = 0; column < run.count; ++column) {
            uint32_t weight = 0;
            for (uint32_t layer = 0; layer < view.layers; ++layer) {
                weight += scratch.totals[layer][column];
            }
            scratch.weights[column] = weight;
        }
        return true;
    }

    // The slice's items in tile order: a whole tile one, a cut tile its bands (cut
    // from its histograms summed over the cores and the layers). Their count; 0 when
    // a wait gave up (recorded).
    template <typename Core>
    uint32_t slice_items(
        const Core& core,
        const SumView& view,
        SumScratch& scratch,
        SliceTiles run,
        uint32_t slice
    ) {
        plan_bands(scratch.weights, run.count, view.heavy, scratch.bands);
        uint32_t count = 0, entries = 0;
        for (uint32_t column = 0; column < run.count; ++column) {
            const uint32_t tile = run.first + column;
            scratch.item_of[column] = count;
            uint32_t bounds[kBandsMost + 1] = {0, kTileRows};
            uint32_t bands = 1;
            if (scratch.bands[column] > 1) {
                if (!sum_hists(core, view, scratch, tile)) {
                    return 0;
                }
                uint32_t starts[kGroups], ends[kGroups];
                for (uint32_t group = 0; group < kGroups; ++group) {
                    starts[group] = ends[group] = 0;
                    for (uint32_t layer = 0; layer < view.layers; ++layer) {
                        starts[group] += scratch.starts[layer][group];
                        ends[group] += scratch.ends[layer][group];
                    }
                }
                bands = cut_rows(starts, ends, scratch.bands[column], bounds);
            }
            scratch.bands[column] = bands;
            for (uint32_t band = 0; band < bands; ++band) {
                Item& item = scratch.items[count++];
                item.tile = tile;
                item.rows = bounds[band] | bounds[band + 1] << kBandRowsEndShift;
                item.column = column;
                item.entry = bands > 1 ? slice * kSliceRecords + entries++ : 0;
                item.weight = 0;
                for (uint32_t layer = 0; layer < TR_LAYERS; ++layer) {
                    uint32_t layer_entries = 0;
                    if (layer < view.layers) {
                        layer_entries = bands > 1 ? band_entries(
                                                        scratch.starts[layer],
                                                        scratch.ends[layer],
                                                        bounds[band],
                                                        bounds[band + 1]
                                                    )
                                                  : scratch.totals[layer][column];
                    }
                    item.entries[layer] = layer_entries;
                    item.weight += layer_entries;
                }
            }
        }
        return count;
    }

    // The slice's records (in order) and its words written. False: gave up.
    template <typename Core>
    bool slice_out(
        const Core& core,
        const SumView& view,
        SumScratch& scratch,
        uint32_t slice,
        uint32_t count
    ) {
        uint32_t weight = 0;
        for (uint32_t k = 0; k < count; ++k) {
            const Item& item = scratch.items[scratch.order[k]];
            record_of(item, view.layers, scratch.records[k]);
            weight += item.weight;
            noc_async_write(
                l1_of(scratch.records[k]),
                dram(0, view.records, TR_NUMBER(slice, k), kRecordBytes),
                kRecordBytes
            );
        }
        for (uint32_t word = 0; word < TS_WORDS; ++word) {
            scratch.slice[word] = 0;
        }
        scratch.slice[TS_RECORDS] = count;
        scratch.slice[TS_WEIGHT] = weight;
        for (uint32_t layer = 0; layer < view.layers; ++layer) {
            scratch.slice[TS_ENTRIES(layer)] = scratch.list_totals[layer];
        }
        asm volatile("fence" ::: "memory");  // the images' stores before the writes
        noc_async_write(
            l1_of(scratch.slice),
            dram(view.bank, view.slice_words, slice, kSliceBytes),
            kSliceBytes
        );
        return sent(core, kWhereSumSent);
    }

    // Layer `layer`'s first positions of every core in the slice's items (its run of
    // tile words and its band entries), written to each core's positions page.
    template <typename Core>
    bool slice_positions(
        const Core& core,
        const SumView& view,
        SumScratch& scratch,
        SliceTiles run,
        uint32_t slice,
        uint32_t count,
        uint32_t layer
    ) {
        for (uint32_t i = 0; i < count; ++i) {
            scratch.run[i] = scratch.items[i].slot[layer];
        }
        uint32_t band_entries_used = 0;
        for (uint32_t i = 0; i < count; ++i) {
            band_entries_used += scratch.bands[scratch.items[i].column] > 1 ? 1 : 0;
        }
        const uint32_t tiles_at = 4 * kSliceTilesMost * slice;
        const uint32_t bands_at = 4 * kPosTileWords +
            4 * kBandWords * kSliceRecords * slice;
        const uint32_t band_bytes = (4 * kBandWords * band_entries_used + kLine - 1) &
            ~(kLine - 1);
        for (uint32_t first = 0; first < view.cores; first += kSumCores) {
            const uint32_t left = view.cores - first;
            const uint32_t cores = left < kSumCores ? left : kSumCores;
            if (!read_counts(core, view, scratch, layer, run, first, cores)) {
                return false;
            }
            for (uint32_t c = 0; c < cores; ++c) {
                for (uint32_t column = 0; column < kSliceTilesMost; ++column) {
                    scratch.tile_images[c][column] = 0;
                }
                for (uint32_t column = 0; column < run.count; ++column) {
                    const uint32_t item = scratch.item_of[column];
                    if (scratch.bands[column] > 1) {
                        scratch.tile_images[c][column] = kPosCut |
                            scratch.bands[column] << kPosBandsShift |
                            scratch.items[item].entry;
                        continue;
                    }
                    scratch.tile_images[c][column] = scratch.run[item];
                    scratch.run[item] += count_at(scratch, run, c, column);
                }
            }
            for (uint32_t column = 0; column < run.count; ++column) {
                if (scratch.bands[column] < 2) {
                    continue;
                }
                if (!read_hists(
                        core, view, scratch, run.first + column, first, cores
                    )) {
                    return false;
                }
                const uint32_t item = scratch.item_of[column];
                for (uint32_t c = 0; c < cores; ++c) {
                    const volatile uint16_t* counts = hist_at(scratch, c, layer);
                    for (uint32_t band = 0; band < scratch.bands[column]; ++band) {
                        const Item& cut = scratch.items[item + band];
                        uint32_t* entry = scratch.band_images[c] +
                            kBandWords * (cut.entry - slice * kSliceRecords);
                        entry[0] = cut.rows;
                        entry[1] = scratch.run[item + band];
                        scratch.run[item + band] += band_entries(
                            counts,
                            counts + kGroups,
                            first_row(cut.rows),
                            end_row(cut.rows)
                        );
                    }
                }
            }
            asm volatile("fence" ::: "memory");  // the images' stores before the writes
            for (uint32_t c = 0; c < cores; ++c) {
                noc_async_write(
                    l1_of(scratch.tile_images[c]),
                    dram(0, view.positions[layer], first + c, kPositionBytes, tiles_at),
                    4 * kSliceTilesMost
                );
                if (band_bytes != 0) {
                    noc_async_write(
                        l1_of(scratch.band_images[c]),
                        dram(
                            0,
                            view.positions[layer],
                            first + c,
                            kPositionBytes,
                            bands_at
                        ),
                        band_bytes
                    );
                }
            }
            if (!sent(core, kWhereSumSent)) {
                return false;
            }
        }
        return true;
    }

    // One slice's sum, whole. False: gave up (recorded).
    template <typename Core>
    bool slice_sum(
        const Core& core, const SumView& view, SumScratch& scratch, uint32_t slice
    ) {
        const SliceTiles run = tiles_of_slice(view.slices, slice);
        if (!slice_totals(core, view, scratch, run)) {
            return false;
        }
        const uint32_t count = slice_items(core, view, scratch, run, slice);
        if (count == 0) {
            return false;
        }
        order_items(
            scratch.items, count, view.layers, scratch.order, scratch.list_totals
        );
        if (!slice_out(core, view, scratch, slice, count)) {
            return false;
        }
        for (uint32_t layer = 0; layer < view.layers; ++layer) {
            if (view.positions[layer] == 0) {
                continue;
            }
            if (!slice_positions(core, view, scratch, run, slice, count, layer)) {
                return false;
            }
        }
        return true;
    }

    // The view's words from the frame's page (the command's block). False: the page is
    // missing or past the capacity (recorded).
    template <typename Core>
    bool sum_view(const Core& core, const km_command_t& command, SumView& view) {
        const km::Block block = core.block(command);
        if (block.bytes < 4 * TF_STEP_AT) {
            return core.gave_up_at(km::kGaveBadItem, kWhereNoPage, __LINE__);
        }
        const volatile uint32_t* page = block.words;
        view.slices = slices_of(page);
        view.layers = layers_of(page);
        if (view.slices.count == 0 || page[TF_LAYER_COUNT] > TR_LAYERS) {
            return core.gave_up_at(km::kGaveBadItem, kWhereSlice, __LINE__);
        }
        view.heavy = page[TF_HEAVY];
        view.cores = km::count(command);
        view.rank = core.me() - km::first(command);
        view.bank = bank_word(page[TF_GRID]);
        view.records = page[TF_RECORDS];
        view.slice_words = page[TF_SLICES];
        for (uint32_t layer = 0; layer < view.layers; ++layer) {
            view.counts[layer] = layer_word(page, layer, TF_L_COUNTS);
            view.rows[layer] = layer_word(page, layer, TF_L_ROWS);
            view.positions[layer] = layer_word(page, layer, TF_L_POSITIONS);
        }
        return true;
    }

    // The sums' command on each mover: the slices rank, rank + cores, ... of this core,
    // turn t on mover A when t is even, on mover B when odd. `scratch` this mover's
    // own field (kinds of SumScratch).
    template <typename Core>
    bool sums_run(const Core& core, const km_command_t& command, uint32_t scratch_at) {
        SumView view;
        if (!sum_view(core, command, view)) {
            return false;
        }
        SumScratch& scratch = *reinterpret_cast<SumScratch*>(scratch_at);
        uint32_t turn = 0;
        for (
            uint32_t slice = view.rank; slice < view.slices.count;
            slice += view.cores, ++turn
        ) {
            if (turn % 2 != km::kMover) {
                continue;
            }
            if (!slice_sum(core, view, scratch, slice)) {
                return false;
            }
        }
        return true;
    }

}  // namespace geometry_k
