// Visibility, the tile thread's first step: every layer's records walked as the list
// pass streams them, the layer's planes (depth, red, green, blue, triangle) filled in
// Dst on the pack CPU with the tie-deciding row and copied to the layer's pages of the
// plane frame.visibility; the unpack CPU hands the blocks on.
#pragma once

#include <stdint.h>

#include "../../../../core/include/thread/frame.h"
#include "../../../../core/include/thread/record.h"
#include "lists.hpp"
#if defined(TRISC_PACK)
#include "row.hpp"
#endif

namespace visibility_step {

    using fill_k::kOutPageBytes;
    using fill_k::kPlanes;
    using fill_k::kPlaneWords;
    using fill_k::kRowBytes;
    using fill_k::kSlotWords;

    // The layer always filled, with or without entries: its planes are the frame's.
    constexpr uint32_t kFirstLayer = 0;

    // Layer `layer`'s kPlanes pages in the plane whose first page is at `visibility`.
    constexpr uint32_t layer_planes(uint32_t visibility, uint32_t layer) {
        return visibility + layer * kPlanes * kOutPageBytes;
    }

    // The frame's layers a record can hold.
    inline uint32_t layer_count(const volatile uint32_t* page) {
        const uint32_t layers = page[TF_LAYER_COUNT];
        return layers < TR_LAYERS ? layers : TR_LAYERS;
    }

#if defined(TRISC_PACK)
    // Stores to L1 finished: a fence, then a load of the last word written used.
    inline void landed(uint32_t address, uint32_t words) {
        asm volatile("fence" ::: "memory");
        const uint32_t last_word = (reinterpret_cast<volatile uint32_t*>(
            address
        )[words - 1]);
        asm volatile("and x0, x0, %0" : : "r"(last_word) : "memory");
    }

    // The tile's header slot as FILL's walk reads it; its count is not 0, so the walk
    // writes nothing out of the header.
    template <typename Tile>
    inline void header_of(const Tile& tile, uint32_t* slot) {
        for (uint32_t word = 0; word < kSlotWords; ++word) {
            slot[word] = 0;
        }
        slot[0] = fill_k::kMarkTile;
        slot[fill_k::kHdrTile] = tile.tile;
        slot[fill_k::kHdrCount] = 1;
        slot[fill_k::kHdrRow0] = tile.first_row;
        slot[fill_k::kHdrRow1] = tile.end_row;
    }

    // One layer on the pack CPU: its planes begun, its records' rows, the band's rows
    // of its planes to `destination`. False: a bad header (recorded) or a wait gave up.
    template <typename Ctx, typename Tile>
    bool fill_layer(
        const Ctx& ctx,
        fill_k::Walk& walk,
        const Tile& tile,
        uint32_t layer,
        uint32_t destination
    ) {
        uint32_t header[kSlotWords];
        header_of(tile, header);
        list_step::ListStream<Ctx> list(ctx, tile.slot[layer], tile.entries[layer]);
        if (!walk.header(header)) {
            list_step::drain_rest(list);
            return false;
        }
        while (const volatile uint32_t* record = list.next()) {
            visibility_step::record(walk, record);
        }
        if (!list.end_walk()) {
            return false;
        }
        ckernel::tensix_sync();
        fill_k::copy_band(destination, tile.first_row, tile.end_row);
        const uint32_t first_word = kRowBytes / 4 * tile.first_row;
        landed(
            destination + 4 * ((kPlanes - 1) * kPlaneWords + first_word),
            kRowBytes / 4 * (tile.end_row - tile.first_row)
        );
        return true;
    }
#endif

}  // namespace visibility_step

#if defined(COMPILE_FOR_TRISC)
// Visibility of `tile` on each compute CPU: the first layer always, every other layer
// with entries, in layer order, as the pass streams them; each layer's planes at its
// pages of `planes.frame_visibility`. False: gave up (recorded).
template <typename Ctx, typename Tile, typename Planes>
bool visibility_compute(Ctx& ctx, const Tile& tile, Planes& planes) {
    using namespace visibility_step;
    const uint32_t layers = layer_count(ctx.page);
    bool filled = true;
#if defined(TRISC_PACK)
    fill_k::Walk walk{ctx.compute};
    walk.start(0, ctx.page[TF_GRID]);
#endif
    for (uint32_t layer = 0; layer < layers; ++layer) {
        if (tile.entries[layer] == 0 && layer != kFirstLayer) {
            continue;
        }
#if defined(TRISC_PACK)
        filled = fill_layer(
                     ctx,
                     walk,
                     tile,
                     layer,
                     layer_planes(planes.frame_visibility, layer)
                 ) &&
            filled;
#else
        filled = list_step::ListStream<Ctx>(ctx, tile.slot[layer], tile.entries[layer])
                     .run() &&
            filled;
#endif
    }
#if defined(TRISC_PACK)
    fill_k::fill::finish();
#else
    static_cast<void>(planes);
#endif
    return filled;
}
#endif
