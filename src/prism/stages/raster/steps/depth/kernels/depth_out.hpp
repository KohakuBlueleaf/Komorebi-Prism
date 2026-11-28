// The DEPTH view's depth_out step: the pack CPU pushes the tile's 1/z plane (a band:
// its rows) as a block of output `depth` for the tile's page of the view's target; the
// data-movement CPU that takes it turns it row-major (SHOW's COPY,
// post/show/kernels/convert.hpp plane_rows) in place and, when the view has levels,
// writes the band's 16 x 16 rows (a whole tile: every level and its top) to the tile's
// slot (thread/depth_levels.h). With T (word transmit, transmit.h) the pack CPU pushes
// the band's rows of the tile's T block too, from the glass layer's red, green and blue
// pages (the material step's), every texel 1 when the tile has no glass; the mover
// writes it as it is.
#pragma once

#include <stdint.h>

#include "../../../../post/show/steps/kernels/out_block.hpp"
#include "../../../../post/show/steps/kernels/post_step.h"

#if defined(PRISM_TF_DEPTH_OUT_TRANSMIT)
#include "../../../../../core/include/thread/transmit.h"
#if defined(TRISC_PACK)
#include "../../../../material/texture/kernels/transmit.hpp"
#endif
#endif

#if !defined(COMPILE_FOR_TRISC)
#include "api/dataflow/dataflow_api.h"
#include "komorebi/device/km_worker.hpp"
#include "../../../../post/show/kernels/convert.hpp"
#include "../../../../../core/include/thread/depth_levels.h"
#endif

namespace depth_out_step {

    using namespace post_step;

#if defined(TRISC_PACK) && defined(PRISM_TF_DEPTH_OUT_TRANSMIT)
    // The band's rows of the tile's T block pushed as a block of output `depth`: the
    // view's glass layer its last (its pages of `visibility`), T 1 when it has no
    // slots in the tile. False: gave up (recorded).
    template <typename Ctx, typename Tile>
    bool push_transmit(Ctx& ctx, const Tile& tile, uint32_t visibility) {
        const uint32_t layers = ctx.page[TF_LAYER_COUNT];
        const uint32_t glass = layers < TR_LAYERS ? layers - 1u : TR_LAYERS - 1u;
        const uint32_t channels = ctx.page[PRISM_TF_DEPTH_OUT_TRANSMIT_CHANNELS];
        const uint32_t base = ctx.page[PRISM_TF_DEPTH_OUT_TRANSMIT_BASE];
        if (tile.page < base || layers == 0 || (channels != 1 && channels != 3)) {
            const compute_mail::Stops stops = {
                ctx.compute.control(),
                fill_k::kGaveWait,
                fill_k::kGaveBadItem,
                kWhereDepthPage,
                kWhereDepthPage,
                kWhereDepthPage
            };
            compute_mail::stop(stops, stops.gave_bad, kWhereDepthPage);
            return false;
        }
        const uint32_t block = prism_frame::out_reserve(
            ctx, prism_frame::kFrameOutDepth
        );
        if (block == 0) {
            return false;
        }
        const uint32_t t = tile.entries[glass] != 0
            ? visibility + glass * fill_k::kPlanes * fill_k::kOutPageBytes
            : 0u;
        const uint32_t bytes = transmit_k::t_codes(
            t == 0 ? 0u : t + fill_k::kOutPageBytes,
            tile.first_row,
            tile.end_row,
            channels,
            block + FO_HEADER_BYTES
        );
        const TransmitPlace place = transmit_place(
            ctx.page[PRISM_TF_DEPTH_OUT_TRANSMIT] - 1u, tile.page - base, channels
        );
        prism_frame::out_push(
            ctx,
            prism_frame::kFrameOutDepth,
            block,
            place.page,
            place.offset + tile.first_row / 2u * transmit_row_bytes(channels),
            bytes,
            kPostPageBytes
        );
        return true;
    }
#endif

    // The depth_out step on a compute CPU (all three call it). False: gave up
    // (recorded).
    template <typename Ctx, typename Tile, typename Planes>
    bool depth_out_compute(Ctx& ctx, const Tile& tile, Planes& planes) {
#if defined(TRISC_PACK)
#if defined(PRISM_TF_DEPTH_OUT_TRANSMIT)
        return push_planes(
                   ctx,
                   prism_frame::kFrameOutDepth,
                   kWhereDepthPage,
                   tile,
                   planes.frame_visibility,
                   1,
                   ctx.page[PRISM_TF_DEPTH_OUT_PAGES]
               ) &&
            (ctx.page[PRISM_TF_DEPTH_OUT_TRANSMIT] == 0 ||
             push_transmit(ctx, tile, planes.frame_visibility));
#else
        return push_planes(
            ctx,
            prism_frame::kFrameOutDepth,
            kWhereDepthPage,
            tile,
            planes.frame_visibility,
            1,
            ctx.page[PRISM_TF_DEPTH_OUT_PAGES]
        );
#endif
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
    // The levels of the rows [first_row, end_row) (both even) row-major at `rows` into
    // the scratch page `out`, written to the tile's slot: the band's 16 x 16 rows, or a
    // whole tile's every level and its top. The loop's wait for the block's write
    // covers these.
    template <typename Ctx>
    void depth_out_levels(
        Ctx& ctx, uint32_t rows, uint32_t first_row, uint32_t end_row, uint32_t out
    ) {
        const tt_l1_ptr uint32_t* from = reinterpret_cast<const tt_l1_ptr uint32_t*>(
            rows
        );
        tt_l1_ptr uint32_t* slot = reinterpret_cast<tt_l1_ptr uint32_t*>(out);
        for (uint32_t y = first_row / 2u; y < end_row / 2u; y++) {
            const tt_l1_ptr uint32_t* a = from + (2u * y - first_row) * 32u;
            for (uint32_t x = 0; x < 16u; x++) {
                slot[DEPTH_LEVELS_L1 + 16u * y + x] = depth_levels_most(
                    depth_levels_most(a[2u * x], a[2u * x + 1u]),
                    depth_levels_most(a[32u + 2u * x], a[33u + 2u * x])
                );
            }
        }
        const volatile tt_l1_ptr uint32_t* header = km::l1(rows - FO_HEADER_BYTES);
        const uint32_t index = header[FO_PAGE] +
            ctx.word(PRISM_TF_DEPTH_OUT_LEVELS_SHIFT);
        const InterleavedAddrGen<true> slots = {
            .bank_base_address = ctx.word(PRISM_TF_DEPTH_OUT_LEVELS),
            .page_size = DEPTH_LEVELS_SLOT_BYTES
        };
        if (first_row != 0 || end_row != DEPTH_LEVELS_TILE) {
            noc_async_write(
                out + first_row * 32u,
                slots.get_noc_addr(index, first_row * 32u),
                (end_row - first_row) * 32u
            );
            return;
        }
        depth_levels_below(reinterpret_cast<uint32_t*>(out));
        noc_async_write(out, slots.get_noc_addr(index), DEPTH_LEVELS_WRITTEN);
        tt_l1_ptr uint32_t* top = slot + DEPTH_LEVELS_WRITTEN / 4u;
        top[DEPTH_LEVELS_TOP_VALUE] = slot[DEPTH_LEVELS_L5];
        top[DEPTH_LEVELS_TOP_WHOLE] = 1u;
        const InterleavedAddrGen<true> tops = {
            .bank_base_address = ctx.word(PRISM_TF_DEPTH_OUT_TOPS),
            .page_size = DEPTH_LEVELS_TOP_BYTES
        };
        noc_async_write(
            out + DEPTH_LEVELS_WRITTEN, tops.get_noc_addr(index), DEPTH_LEVELS_TOP_BYTES
        );
    }

    template <typename Ctx>
    uint32_t depth_out_convert(Ctx& ctx, uint32_t payload, uint32_t bytes) {
#if defined(PRISM_TF_DEPTH_OUT_TRANSMIT)
        const volatile tt_l1_ptr uint32_t* header = km::l1(payload - FO_HEADER_BYTES);
        const uint32_t transmit = ctx.word(PRISM_TF_DEPTH_OUT_TRANSMIT);
        if (transmit != 0 && header[FO_PAGE] >= transmit - 1u) {
            return bytes;  // a T block: written as it is
        }
#endif
        uint32_t first_row = 0, end_row = 0;
        rows_of(payload, bytes, first_row, end_row);
        const uint32_t out = scratch_page(ctx.kept(prism_frame::kKeptDepthOutScratch));
        show_k::plane_rows(
            reinterpret_cast<const tt_l1_ptr uint32_t*>(payload),
            reinterpret_cast<tt_l1_ptr uint32_t*>(out),
            first_row,
            end_row
        );
        const uint32_t copied = copy_back(
            out + first_row * fill_k::kRowBytes, payload, bytes
        );
        if (ctx.word(PRISM_TF_DEPTH_OUT_LEVELS) != 0) {
            depth_out_levels(ctx, payload, first_row, end_row, out);
        }
        return copied;
    }
#endif

}  // namespace depth_out_step

// The loop calls a step's functions unqualified.
using depth_out_step::depth_out_compute;
#if !defined(COMPILE_FOR_TRISC)
using depth_out_step::depth_out_convert;
#endif
