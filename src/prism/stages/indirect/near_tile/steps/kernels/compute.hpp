// The near tile step on the compute CPUs: the pack CPU asks the tile's pages of the
// light pages and the upsample's weights into the plane near.light and marks it on (or
// marks it off), the unpack CPU serves its mails; the math CPU has no part.
#pragma once

#include <stdint.h>

#include "../../../../../core/include/compute_mail.hpp"
#include "../../../../../core/include/thread/frame.h"
#include "../../../../../core/include/thread/record.h"
#include "../../../../../program/frame/kernels/pack.hpp"
#include "near_tile_step.h"

namespace near_tile_step {

    // The step's waits: its give-up places, the compute threads' code and limit.
    inline compute_mail::Waits waits_of(uint32_t control) {
        return {
            {control,
             fill_k::kGaveWait,
             fill_k::kGaveBadItem,
             kWhereNearTileBad,
             kWhereNearTileBad,
             kWhereNearTileBad},
            fill_k::kWaitCycles
        };
    }

#if defined(TRISC_PACK)
    // The tile's light page and upsample page into `plane`, and its mark. False: gave
    // up.
    template <typename Ctx, typename Tile>
    bool near_pack(Ctx& ctx, const Tile& tile, uint32_t plane) {
        volatile uint32_t* words = reinterpret_cast<volatile uint32_t*>(plane);
        const bool on = ctx.page[PRISM_TF_NEAR_TILE_ON] != 0;
        words[kNearOn] = 0;
        if (!on) {
            return true;
        }
        const uint32_t light = prism_frame::ask_begin(
            ctx, ctx.page[PRISM_TF_NEAR_TILE_LIGHT], kNearPageBytes
        );
        if (light == 0) {
            return false;
        }
        prism_frame::ask_entry(light, 0, tile.tile, plane);
        const uint32_t light_half = prism_frame::ask_post(ctx, light, 1);
        const uint32_t weights = prism_frame::ask_begin(
            ctx, ctx.page[PRISM_TF_NEAR_TILE_UPSAMPLE], kNearWeightsBytes
        );
        if (weights == 0) {
            return false;
        }
        prism_frame::ask_entry(weights, 0, tile.tile, plane + kNearPageBytes);
        const uint32_t weights_half = prism_frame::ask_post(ctx, weights, 1);
        if (!prism_frame::ask_wait(ctx, light_half) ||
            !prism_frame::ask_wait(ctx, weights_half)) {
            return false;
        }
        words[kNearOn] = 1;
        return true;
    }
#endif

}  // namespace near_tile_step

// The near tile step on a compute CPU (all three call it). False: gave up (recorded).
template <typename Ctx, typename Tile, typename Planes>
bool near_tile_compute(Ctx& ctx, const Tile& tile, Planes& planes) {
#if defined(TRISC_PACK)
    const bool done = near_tile_step::near_pack(ctx, tile, planes.near_light);
    compute_mail::end_mails();
    return done;
#else
    static_cast<void>(tile);
    static_cast<void>(planes);
#if defined(TRISC_UNPACK)
    compute_mail::serve_mails(near_tile_step::waits_of(ctx.compute.control()));
#else
    static_cast<void>(ctx);
#endif
    return true;
#endif
}
