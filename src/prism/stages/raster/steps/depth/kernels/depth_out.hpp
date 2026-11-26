// The DEPTH view's depth_out step: the pack CPU pushes the tile's 1/z plane (a band:
// its rows) as a block of output `depth` for the tile's page of the view's target; the
// data-movement CPU that takes it turns it row-major (SHOW's COPY,
// post/show/kernels/convert.hpp plane_rows) in place.
#pragma once

#include <stdint.h>

#include "../../../../post/show/steps/kernels/out_block.hpp"
#include "../../../../post/show/steps/kernels/post_step.h"

#if !defined(COMPILE_FOR_TRISC)
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
        return push_planes(
            ctx,
            prism_frame::kFrameOutDepth,
            kWhereDepthPage,
            tile,
            planes.frame_visibility,
            1,
            ctx.page[PRISM_TF_DEPTH_OUT_PAGES]
        );
#else
        static_cast<void>(ctx);
        static_cast<void>(tile);
        static_cast<void>(planes);
        return true;
#endif
    }

#if !defined(COMPILE_FOR_TRISC)
    // The block whose payload is at `payload` (the band's rows of the tile's 1/z plane,
    // `bytes` of them) row-major through this CPU's scratch page, back over the
    // payload; the bytes.
    template <typename Ctx>
    uint32_t depth_out_convert(Ctx& ctx, uint32_t payload, uint32_t bytes) {
        uint32_t first_row = 0, end_row = 0;
        rows_of(payload, bytes, first_row, end_row);
        const uint32_t out = scratch_page(ctx.kept(prism_frame::kKeptDepthOutScratch));
        show_k::plane_rows(
            reinterpret_cast<const tt_l1_ptr uint32_t*>(payload),
            reinterpret_cast<tt_l1_ptr uint32_t*>(out),
            first_row,
            end_row
        );
        return copy_back(out + first_row * fill_k::kRowBytes, payload, bytes);
    }
#endif

}  // namespace depth_out_step
