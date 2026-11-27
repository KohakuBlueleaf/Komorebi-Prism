// The step `walk`: its list pass's blocks taken and popped on every compute CPU, one
// page asked into its kept space, one output block of it pushed; its begin and its
// convert on the movers.
#pragma once

#include <stdint.h>

namespace prism_frame {
#if defined(COMPILE_FOR_TRISC)
    // A layer's list blocks waited for and popped (the pack CPU reads none).
    inline bool walk_layer(ComputeContext& ctx, const Tile& tile, uint32_t layer) {
        const ListSpan span = span_of(tile.slot[layer], tile.entries[layer]);
        for (uint32_t block = 0; block < span.blocks; block++) {
            const uint32_t left = span.pages - block * kFrameBlockPages;
            const uint32_t pages = left < kFrameBlockPages ? left : kFrameBlockPages;
            const uint32_t half = km::block_half(kListPair, kListPattern, block);
            if (!ctx.compute.wait_front(half, pages)) {
                return false;
            }
            cb_pop_front(half, pages);
        }
        return true;
    }

    inline bool walk_compute(ComputeContext& ctx, const Tile& tile, Planes& planes) {
        static_cast<void>(planes);
        for (uint32_t at = 0; at < kWalkPass0LayersCount; at++) {
            if (!walk_layer(ctx, tile, kWalkPass0Layers[at])) {
                return false;
            }
        }
#if defined(TRISC_PACK)
        const uint32_t space = ctx.kept(kKeptWalkSpace);
        const uint32_t ask = ask_begin(ctx, ctx.word(TF_RECORDS), TR_WORDS * 4);
        if (ask == 0) {
            return false;
        }
        ask_entry(ask, 0, tile.number, space);
        if (!ask_wait(ctx, ask_post(ctx, ask, 1))) {
            return false;
        }
        const uint32_t block = out_reserve(ctx, 0);
        if (block == 0) {
            return false;
        }
        volatile uint32_t* payload = (reinterpret_cast<volatile uint32_t*>(
            block + FO_HEADER_BYTES
        ));
        payload[0] = reinterpret_cast<volatile uint32_t*>(space)[0];
        out_push(ctx, 0, block, tile.page, 0, TR_WORDS * 4, TR_WORDS * 4);
#endif
        return true;
    }

    inline bool walk_variant(ComputeContext& ctx, const Tile& tile, Planes& planes) {
        return walk_compute(ctx, tile, planes);
    }
#else
    inline bool walk_begin(MoverContext& ctx) {
        static_cast<void>(ctx.kept(kKeptWalkSpace));
        return true;
    }

    inline uint32_t walk_convert(MoverContext& ctx, uint32_t payload, uint32_t bytes) {
        static_cast<void>(ctx);
        static_cast<void>(payload);
        return bytes;
    }
#endif
}  // namespace prism_frame
