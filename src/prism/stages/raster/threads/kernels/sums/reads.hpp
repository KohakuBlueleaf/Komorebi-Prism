// The sums' reads and writes of the cores' pages, on a mover: a slice's run of a
// layer's counts of up to kSumCores cores, a tile's row histograms of every layer of
// them, and the images written back. Every DRAM access starts and ends on a line; an
// L1 image sits at its destination's offset in the line.
#pragma once

#include <stdint.h>

#include "../frame.hpp"
#include "../waits.hpp"
#include "slice.hpp"

namespace geometry_k {

    // Bytes of L1 a core's run of counts takes in the read buffer: its lines.
    constexpr uint32_t kRunBytes = 4 * kLine;
    static_assert(kCountTileBytes * kSliceTilesMost + kLine <= kRunBytes);

    // An L1 address as the NoC calls take it.
    inline uint32_t l1_of(const volatile void* pointer) {
        return static_cast<uint32_t>(reinterpret_cast<uintptr_t>(pointer));
    }

    // A mover's scratch for one slice (in its own raw field).
    struct SumScratch {
        uint32_t totals[TR_LAYERS][kSliceTilesMost];
        uint32_t weights[kSliceTilesMost];
        uint32_t bands[kSliceTilesMost];
        uint32_t item_of[kSliceTilesMost];  // a tile's first item
        uint32_t starts[TR_LAYERS][kGroups], ends[TR_LAYERS][kGroups];
        uint32_t run[kSliceRecords];  // an item's next position over the cores
        uint32_t order[kSliceRecords];
        uint32_t list_totals[TR_LAYERS];
        Item items[kSliceRecords];
        alignas(64) uint8_t counts[kSumCores][kRunBytes];
        alignas(64) uint8_t hists[kSumCores][TR_LAYERS][kHistTileBytes];
        alignas(64) uint32_t tile_images[kSumCores][kSliceTilesMost];
        alignas(64) uint32_t band_images[kSumCores][kBandWords * kSliceRecords];
        alignas(64) uint32_t records[kSliceRecords][TR_WORDS];
        alignas(64) uint32_t slice[TS_WORDS];
    };

    // The view's words a slice's sum needs, read once from the frame's page.
    struct SumView {
        Slices slices;
        uint32_t layers, heavy, cores, rank, bank;
        uint32_t records, slice_words, page_first, page_across;
        uint32_t counts[TR_LAYERS], rows[TR_LAYERS], positions[TR_LAYERS];
    };

    // Counts of tiles [first, first + tiles) of layer `layer` of cores [core, core +
    // cores) into the scratch, each core's run at its offset in its lines. False: gave
    // up (recorded).
    template <typename Core>
    bool read_counts(
        const Core& core,
        const SumView& view,
        SumScratch& scratch,
        uint32_t layer,
        SliceTiles run,
        uint32_t first_core,
        uint32_t cores
    ) {
        const uint32_t offset = kCountTileBytes * run.first;
        const uint32_t start = offset & ~(kLine - 1);
        const uint32_t end = (offset + kCountTileBytes * run.count + kLine - 1) &
            ~(kLine - 1);
        for (uint32_t c = 0; c < cores; ++c) {
            noc_async_read(
                dram(0, view.counts[layer], first_core + c, kCountBytes, start),
                l1_of(scratch.counts[c]),
                end - start
            );
        }
        if (!landed(core, kWhereSumRead)) {
            return false;
        }
        invalidate_l1_cache();
        return true;
    }

    // Core c's (of the batch) count of the run's tile `column`, after read_counts.
    inline uint32_t count_at(
        const SumScratch& scratch, SliceTiles run, uint32_t c, uint32_t column
    ) {
        const uint32_t offset = kCountTileBytes * run.first;
        const volatile uint32_t* words = reinterpret_cast<const volatile uint32_t*>(
            scratch.counts[c] + offset % kLine
        );
        return words[column];
    }

    // Row histograms of tile `tile` of every layer of cores [first_core, first_core +
    // cores) into the scratch. False: gave up (recorded).
    template <typename Core>
    bool read_hists(
        const Core& core,
        const SumView& view,
        SumScratch& scratch,
        uint32_t tile,
        uint32_t first_core,
        uint32_t cores
    ) {
        for (uint32_t c = 0; c < cores; ++c) {
            for (uint32_t layer = 0; layer < view.layers; ++layer) {
                noc_async_read(
                    dram(
                        0,
                        view.rows[layer],
                        first_core + c,
                        kHistBytes,
                        kHistTileBytes * tile
                    ),
                    l1_of(scratch.hists[c][layer]),
                    kHistTileBytes
                );
            }
        }
        if (!landed(core, kWhereSumRead)) {
            return false;
        }
        invalidate_l1_cache();
        return true;
    }

    // Core c's (of the batch) histogram of layer `layer`: starts at 0, ends at kGroups.
    inline const volatile uint16_t* hist_at(
        const SumScratch& scratch, uint32_t c, uint32_t layer
    ) {
        return reinterpret_cast<const volatile uint16_t*>(scratch.hists[c][layer]);
    }

    // A tile's histograms summed over every core, by layer, into scratch.starts and
    // scratch.ends. False: gave up (recorded).
    template <typename Core>
    bool sum_hists(
        const Core& core, const SumView& view, SumScratch& scratch, uint32_t tile
    ) {
        for (uint32_t layer = 0; layer < TR_LAYERS; ++layer) {
            for (uint32_t group = 0; group < kGroups; ++group) {
                scratch.starts[layer][group] = scratch.ends[layer][group] = 0;
            }
        }
        for (uint32_t first = 0; first < view.cores; first += kSumCores) {
            const uint32_t left = view.cores - first;
            const uint32_t cores = left < kSumCores ? left : kSumCores;
            if (!read_hists(core, view, scratch, tile, first, cores)) {
                return false;
            }
            for (uint32_t c = 0; c < cores; ++c) {
                for (uint32_t layer = 0; layer < view.layers; ++layer) {
                    const volatile uint16_t* counts = hist_at(scratch, c, layer);
                    for (uint32_t group = 0; group < kGroups; ++group) {
                        scratch.starts[layer][group] += counts[group];
                        scratch.ends[layer][group] += counts[kGroups + group];
                    }
                }
            }
        }
        return true;
    }

}  // namespace geometry_k
