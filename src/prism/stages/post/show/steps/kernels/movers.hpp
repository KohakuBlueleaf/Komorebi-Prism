// The post step on the data-movement CPUs: the thresholds and their buckets, and the
// view's words after them in their region (kernels/view.h), kept once a command (the
// loop's begin, before the command's first tile thread), and a block's colour converted
// in place by SHOW's rule (kernels/convert.hpp) on the CPU that took it.
#pragma once

#include <stdint.h>

#include "../../../../../core/include/thread/frame.h"
#include "api/dataflow/dataflow_api.h"
#include "komorebi/device/km_worker.hpp"
#include "../../kernels/convert.hpp"
#include "../../kernels/view.h"
#include "out_block.hpp"

namespace post_step {

    static_assert(
        show_k::kShowTableWords * 4 + show_k::kShowBuckets <= kPostTableBytes
    );
    static_assert(show_k::kShowPageBytes == kPostPageBytes);

    // The kept thresholds (int32) and buckets (a byte each, after them).
    template <typename Ctx>
    int32_t* thresholds_of(Ctx& ctx) {
        return reinterpret_cast<int32_t*>(ctx.kept(prism_frame::kKeptPostTable));
    }

    template <typename Ctx>
    tt_l1_ptr uint8_t* buckets_of(Ctx& ctx) {
        return reinterpret_cast<tt_l1_ptr uint8_t*>(
            ctx.kept(prism_frame::kKeptPostTable) + 4 * show_k::kShowTableWords
        );
    }

    // The thresholds' table read from the regions' bank into this CPU's scratch page,
    // then the kept thresholds and buckets made from it. False: gave up.
    template <typename Ctx>
    bool post_begin(Ctx& ctx) {
        const uint32_t table = ctx.page[PRISM_TF_POST_TABLE];
        if (table == 0) {
            return ctx.gave_up(km::kGaveBadItem, kWherePostTable);
        }
        const uint32_t staging = scratch_page(ctx.kept(prism_frame::kKeptPostScratch));
        noc_async_read(
            get_noc_addr_from_bank_id<true>(ctx.bank, table),
            staging,
            4 * show_k::kShowTableWords
        );
        noc_async_read(
            get_noc_addr_from_bank_id<true>(ctx.bank, table + show_k::kShowPageBytes),
            ctx.kept(prism_frame::kKeptPostView),
            kViewRegionBytes
        );
        const bool arrived = ctx.movement.wait(
            [] {
                return ncrisc_noc_reads_flushed(noc_index);
            },
            kWherePostTable
        );
        if (!arrived) {
            return false;
        }
        show_k::thresholds_of(staging, thresholds_of(ctx), buckets_of(ctx));
        return true;
    }

    // The block whose payload is at `payload` (the band's rows of the tile's red, green
    // and blue planes, `bytes` a plane) converted by SHOW's rule through this CPU's
    // scratch page, back over the payload; the bytes.
    template <typename Ctx>
    uint32_t post_convert(Ctx& ctx, uint32_t payload, uint32_t bytes) {
        uint32_t first_row = 0, end_row = 0;
        rows_of(payload, bytes, first_row, end_row);
        const uint32_t out = scratch_page(ctx.kept(prism_frame::kKeptPostScratch));
        show_k::colour_rows(
            reinterpret_cast<const tt_l1_ptr uint32_t*>(payload),
            reinterpret_cast<tt_l1_ptr uint32_t*>(out),
            first_row,
            end_row,
            thresholds_of(ctx),
            buckets_of(ctx)
        );
        return copy_back(out + first_row * fill_k::kRowBytes, payload, bytes);
    }

}  // namespace post_step

// The loop calls a step's functions unqualified.
using post_step::post_begin;
using post_step::post_convert;
