// The post step on the compute CPUs: the pack CPU pushes the first layer's colour
// planes (a band: its rows) as a block of output `display` (the loop's out_reserve,
// out_push) for the tile's page, through the file's view transform when the kept
// view is on (kernels/view_fetch.hpp: its pages asked into the kept slots by the
// frame's page requests, the unpack CPU serving the pack CPU's mails meanwhile); the
// math CPU has no part.
#pragma once

#include <stdint.h>

#include "../../kernels/show.h"
#include "../../kernels/view.h"
#include "out_block.hpp"
#if defined(TRISC_PACK)
#include "../../kernels/view_fetch.hpp"
#endif

namespace post_step {

#if defined(TRISC_PACK)
    // Pages `pages[0 .. count)` of the cube at bank address `base` into the slots at
    // `slots`, in asks of at most FA_ENTRIES posted to the halves in turn, all waited
    // for. False: gave up.
    inline bool ask_slots(
        prism_frame::ComputeContext& ctx,
        uint32_t base,
        uint32_t slots,
        const uint32_t* pages,
        uint32_t count
    ) {
        uint32_t halves[(kViewSlots + FA_ENTRIES - 1) / FA_ENTRIES];
        uint32_t posted = 0;
        for (uint32_t at = 0; at < count; at += FA_ENTRIES) {
            const uint32_t entries = count - at < FA_ENTRIES ? count - at : FA_ENTRIES;
            const uint32_t ask = prism_frame::ask_begin(ctx, base, kViewPageBytes);
            if (ask == 0) {
                return false;
            }
            for (uint32_t i = 0; i < entries; ++i) {
                prism_frame::ask_entry(
                    ask, i, pages[at + i], slots + (at + i) * kViewPageBytes
                );
            }
            halves[posted++] = prism_frame::ask_post(ctx, ask, entries);
        }
        for (uint32_t i = 0; i < posted; ++i) {
            if (!prism_frame::ask_wait(ctx, halves[i])) {
                return false;
            }
        }
        return true;
    }

    // The band's rows of the colour planes at `rgb` through the view `view` into a
    // block of output `display` for the tile's page, pushed. False: gave up.
    template <typename Ctx, typename Tile>
    bool push_view(Ctx& ctx, const Tile& tile, uint32_t rgb, const uint32_t* view) {
        const compute_mail::Stops stops = {
            ctx.compute.control(),
            fill_k::kGaveWait,
            fill_k::kGaveBadItem,
            kWherePostPage,
            kWherePostPage,
            kWherePostPage
        };
        if (tile.page >= ctx.page[PRISM_TF_POST_PAGES] ||
            !(tile.first_row < tile.end_row) || tile.end_row > 32) {
            compute_mail::stop(stops, stops.gave_bad, kWherePostPage);
            return false;
        }
        const uint32_t block = prism_frame::out_reserve(
            ctx, prism_frame::kFrameOutDisplay
        );
        if (block == 0) {
            return false;
        }
        const uint32_t first_word = (tile.first_row & ~1u) * fill_k::kRowBytes / 4;
        const uint32_t end_word = ((tile.end_row + 1) & ~1u) * fill_k::kRowBytes / 4;
        const uint32_t slots = ctx.kept(prism_frame::kKeptPostSlots);
        view_fetch::ViewCounts counts;
        const bool done = view_fetch::view_planes(
            view,
            reinterpret_cast<const float*>(rgb),
            reinterpret_cast<float*>(block + FO_HEADER_BYTES),
            first_word,
            end_word,
            reinterpret_cast<uint32_t*>(ctx.kept(prism_frame::kKeptPostWork)),
            slots,
            [&](const uint32_t* pages, uint32_t count) {
                return ask_slots(ctx, view[kViewBase], slots, pages, count);
            },
            counts
        );
        if (!done) {
            return false;
        }
        prism_frame::out_push(
            ctx,
            prism_frame::kFrameOutDisplay,
            block,
            tile.page,
            tile.first_row * fill_k::kRowBytes,
            (tile.end_row - tile.first_row) * fill_k::kRowBytes,
            kPostPageBytes
        );
        return true;
    }
#endif

    // The post step on a compute CPU (all three call it). False: gave up (recorded).
    template <typename Ctx, typename Tile, typename Planes>
    bool post_compute(Ctx& ctx, const Tile& tile, Planes& planes) {
#if defined(COMPILE_FOR_TRISC)
        const uint32_t* view = reinterpret_cast<const uint32_t*>(
            ctx.kept(prism_frame::kKeptPostView)
        );
#endif
#if defined(TRISC_PACK)
        const uint32_t rgb = planes.frame_visibility + kShowFirstPlane * kPostPageBytes;
        if (view[kViewOn] != 0) {  // in a window of the pack CPU's mails
            const bool done = push_view(ctx, tile, rgb, view);
            compute_mail::end_mails();
            return done;
        }
        return push_planes(
            ctx,
            prism_frame::kFrameOutDisplay,
            kWherePostPage,
            tile,
            rgb,
            kShowPlanes,
            ctx.page[PRISM_TF_POST_PAGES]
        );
#else
#if defined(TRISC_UNPACK)
        if (view[kViewOn] != 0) {
            compute_mail::serve_mails(prism_frame::waits_at(ctx, kWherePostPage));
        }
#else
        static_cast<void>(ctx);
#endif
        static_cast<void>(tile);
        static_cast<void>(planes);
        return true;
#endif
    }

}  // namespace post_step

// The loop calls a step's functions unqualified.
using post_step::post_compute;
