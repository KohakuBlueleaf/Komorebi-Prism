// The post step on the compute CPUs: the pack CPU pushes the first layer's colour
// planes (a band: its rows) as output `display`'s block, into the ring pair's two
// halves in turn; the unpack and math CPUs have no part.
#pragma once

#include <stdint.h>

#include "../../kernels/show.h"
#include "out_block.hpp"

namespace post_step {

    // The post step on a compute CPU (all three call it). False: gave up (recorded).
    template <typename Ctx, typename Tile, typename Planes>
    bool post_compute(Ctx& ctx, const Tile& tile, Planes& planes) {
#if defined(TRISC_PACK)
        static uint32_t turn = 0;  // the half of the next block
        turn ^= 1u;
        return push_planes(
            ctx.compute.control(),
            kWherePostRing,
            ctx.display[turn],
            planes.frame_visibility + kShowFirstPlane * kPostPageBytes,
            kShowPlanes,
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

}  // namespace post_step
