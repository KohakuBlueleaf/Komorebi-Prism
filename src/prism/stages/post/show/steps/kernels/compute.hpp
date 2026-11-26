// The post step on the compute CPUs: the pack CPU pushes the first layer's colour
// planes (a band: its rows) as a block of output `display` (the loop's out_reserve,
// out_push) for the tile's page; the unpack and math CPUs have no part.
#pragma once

#include <stdint.h>

#include "../../kernels/show.h"
#include "out_block.hpp"

namespace post_step {

    // The post step on a compute CPU (all three call it). False: gave up (recorded).
    template <typename Ctx, typename Tile, typename Planes>
    bool post_compute(Ctx& ctx, const Tile& tile, Planes& planes) {
#if defined(TRISC_PACK)
        return push_planes(
            ctx,
            prism_frame::kFrameOutDisplay,
            kWherePostPage,
            tile,
            planes.frame_visibility + kShowFirstPlane * kPostPageBytes,
            kShowPlanes,
            ctx.page[PRISM_TF_POST_PAGES]
        );
#else
        static_cast<void>(ctx);
        static_cast<void>(tile);
        static_cast<void>(planes);
        return true;
#endif
    }

}  // namespace post_step

// The loop calls a step's functions unqualified.
using post_step::post_compute;
