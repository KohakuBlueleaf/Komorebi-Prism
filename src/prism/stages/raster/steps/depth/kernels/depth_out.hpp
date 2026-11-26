// The DEPTH view's depth_out step: the pack CPU pushes the tile's 1/z plane (a band:
// its rows) as output `depth`'s block; the data-movement CPU that takes it turns it
// row-major (SHOW's COPY, post/show/kernels/convert.hpp plane_rows) into a scratch page
// for the target's page of the tile.
#pragma once

#include <stdint.h>

#include "../../../../post/show/steps/kernels/out_block.hpp"
#include "../../../../post/show/steps/kernels/post_step.h"

#if !defined(COMPILE_FOR_TRISC)
#include "../../../../../core/include/grid.h"
#include "../../../../../core/include/thread/frame.h"
#include "api/dataflow/dataflow_api.h"
#include "komorebi/device/km_worker.hpp"
#include "../../../../post/show/kernels/convert.hpp"
#endif

namespace depth_out_step {

    using namespace post_step;

    // The depth_out step on a compute CPU (all three call it). False: gave up
    // (recorded).
    template <typename Ctx, typename Tile, typename Planes>
    bool depth_out_compute(Ctx& ctx, const Tile& tile, Planes& planes) {
#if defined(TRISC_PACK)
        static uint32_t turn = 0;  // the half of the next block
        turn ^= 1u;
        return push_planes(
            ctx.compute.control(),
            kWhereDepthRing,
            ctx.depth[turn],
            planes.frame_visibility,
            1,
            tile.first_row,
            tile.end_row
        );
#else
        static_cast<void>(ctx);
        static_cast<void>(tile);
        static_cast<void>(planes);
        return true;
#endif
    }

#if !defined(COMPILE_FOR_TRISC)
    // Output `depth`'s block of `tile` row-major into this CPU's next scratch page: the
    // L1 address of the band's rows, their `bytes`, byte `offset` in the target's
    // `page` (first + (tile / tiles a row) across + tile mod tiles a row). 0: gave up.
    template <typename Ctx, typename Tile>
    uint32_t depth_out_convert(
        Ctx& ctx,
        uint32_t block,
        const Tile& tile,
        uint32_t& page,
        uint32_t& bytes,
        uint32_t& offset
    ) {
        static uint32_t used = 0;  // this CPU's scratch pages taken
        const uint32_t row_tiles = grid_of(ctx.page[TF_GRID]).across;
        page = ctx.page[PRISM_TF_DEPTH_OUT_FIRST] +
            tile.tile / row_tiles * ctx.page[PRISM_TF_DEPTH_OUT_ACROSS] +
            tile.tile % row_tiles;
        if (page >= ctx.page[PRISM_TF_DEPTH_OUT_PAGES]) {
            ctx.bad(kWhereDepthPage);
            return 0;
        }
        const uint32_t out = scratch_page(
            ctx, ctx.depth_scratch, used, kWhereDepthSent
        );
        if (out == 0) {
            return 0;
        }
        show_k::plane_rows(
            reinterpret_cast<const tt_l1_ptr uint32_t*>(block),
            reinterpret_cast<tt_l1_ptr uint32_t*>(out),
            tile.first_row,
            tile.end_row
        );
        offset = tile.first_row * fill_k::kRowBytes;
        bytes = (tile.end_row - tile.first_row) * fill_k::kRowBytes;
        return out + offset;
    }
#endif

}  // namespace depth_out_step
