// The post step on the data-movement CPUs: the thresholds and their buckets kept once
// a command (mover A, before the command's first tile thread is handed on), and a
// block's colour converted by SHOW's rule (kernels/convert.hpp) into a scratch page
// on the CPU that took it.
#pragma once

#include <stdint.h>

#include "../../../../../core/include/grid.h"
#include "../../../../../core/include/thread/frame.h"
#include "api/dataflow/dataflow_api.h"
#include "komorebi/device/km_worker.hpp"
#include "../../kernels/convert.hpp"
#include "out_block.hpp"

namespace post_step {

    static_assert(
        show_k::kShowTableWords * 4 + show_k::kShowBuckets <= kPostTableBytes
    );
    static_assert(show_k::kShowPageBytes == kPostPageBytes);

    // The kept thresholds (int32) and buckets (a byte each, after them).
    template <typename Ctx>
    int32_t* thresholds_of(const Ctx& ctx) {
        return reinterpret_cast<int32_t*>(ctx.post_table);
    }

    template <typename Ctx>
    tt_l1_ptr uint8_t* buckets_of(const Ctx& ctx) {
        return reinterpret_cast<tt_l1_ptr uint8_t*>(
            ctx.post_table + 4 * show_k::kShowTableWords
        );
    }

    // The thresholds' table read from the regions' bank into mover A's first scratch
    // page, then the kept thresholds and buckets made from it. False: gave up.
    template <typename Ctx>
    bool post_begin(Ctx& ctx) {
        const volatile uint32_t* page = ctx.page;
        const uint32_t bank_plus_one = bank_word(page[TF_GRID]);
        const uint32_t table = page[PRISM_TF_POST_TABLE];
        if (bank_plus_one == 0 || table == 0) {
            ctx.bad(kWherePostTable);
            return false;
        }
        uint32_t used = 0;
        const uint32_t staging = scratch_page(
            ctx, ctx.post_scratch, used, kWherePostSent
        );
        if (staging == 0) {
            return false;
        }
        noc_async_read(
            get_noc_addr_from_bank_id<true>(bank_plus_one - 1, table),
            staging,
            4 * show_k::kShowTableWords
        );
        const bool arrived = ctx.wait(
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

    // Output `display`'s block of `tile` (its red, green, blue planes) converted into
    // this CPU's next scratch page: the L1 address of the band's rows, their `bytes`
    // and byte `offset` in display page `page`. 0: gave up.
    template <typename Ctx, typename Tile>
    uint32_t post_convert(
        Ctx& ctx,
        uint32_t block,
        const Tile& tile,
        uint32_t& page,
        uint32_t& bytes,
        uint32_t& offset
    ) {
        static uint32_t used = 0;  // this CPU's scratch pages taken
        if (page >= ctx.page[PRISM_TF_POST_PAGES]) {
            ctx.bad(kWherePostPage);
            return 0;
        }
        const uint32_t out = scratch_page(ctx, ctx.post_scratch, used, kWherePostSent);
        if (out == 0) {
            return 0;
        }
        show_k::colour_rows(
            reinterpret_cast<const tt_l1_ptr uint32_t*>(block),
            reinterpret_cast<tt_l1_ptr uint32_t*>(out),
            tile.first_row,
            tile.end_row,
            thresholds_of(ctx),
            buckets_of(ctx)
        );
        offset = tile.first_row * fill_k::kRowBytes;
        bytes = (tile.end_row - tile.first_row) * fill_k::kRowBytes;
        return out + offset;
    }

}  // namespace post_step
