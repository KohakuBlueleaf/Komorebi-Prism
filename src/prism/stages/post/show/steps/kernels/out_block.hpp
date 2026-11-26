// An output block of a step (post, depth_out): on the pack CPU a band's rows of planes
// copied into a block of an output ring; on a data-movement CPU the scratch page a
// block is converted into.
#pragma once

#include <stdint.h>

#include "post_step.h"

#if defined(COMPILE_FOR_TRISC)
#include "../../../../../core/include/compute_mail.hpp"
#include "../../../../raster/kernels/common/layouts.hpp"
#if defined(TRISC_PACK)
#include <riscv_vector.h>
#endif
#else
#include "api/dataflow/dataflow_api.h"
#endif

namespace post_step {

#if defined(COMPILE_FOR_TRISC)
    // The waits of a block's room: every place `where`.
    inline compute_mail::Waits block_waits(uint32_t control, uint32_t where) {
        return {
            {control, fill_k::kGaveWait, fill_k::kGaveBadItem, where, where, where},
            fill_k::kWaitCycles
        };
    }
#endif

#if defined(TRISC_PACK)
    // `planes` planes from L1 `from` (a page each), the row pairs of rows [first_row,
    // end_row), into a block of output ring `cb`, pushed. False: no room in time
    // (given up at `where`).
    inline bool push_planes(
        uint32_t control,
        uint32_t where,
        uint32_t cb,
        uint32_t from,
        uint32_t planes,
        uint32_t first_row,
        uint32_t end_row
    ) {
        const compute_mail::Waits waits = block_waits(control, where);
        if (!compute_mail::reserve(waits, cb, 1)) {
            return false;
        }
        const uint32_t block = compute_mail::write_ptr(cb);
        // two rows of a plane are 256 contiguous bytes (raster.h kRowBytes)
        const uint32_t first_word = (first_row & ~1u) * fill_k::kRowBytes / 4;
        const uint32_t end_word = ((end_row + 1) & ~1u) * fill_k::kRowBytes / 4;
        const size_t vl = __riscv_vsetvl_e32m8(32);
        uint32_t last = block;
        for (uint32_t plane = 0; plane < planes; ++plane) {
            const uint32_t* source = reinterpret_cast<const uint32_t*>(
                from + plane * kPostPageBytes
            );
            uint32_t* target = reinterpret_cast<uint32_t*>(
                block + plane * kPostPageBytes
            );
            for (uint32_t i = first_word; i < end_word; i += 32) {
                __riscv_vse32_v_u32m8(
                    target + i, __riscv_vle32_v_u32m8(source + i, vl), vl
                );
            }
            last = reinterpret_cast<uint32_t>(target + end_word - 1);
        }
        compute_mail::push(cb, last, 1);
        return true;
    }
#endif

#if !defined(COMPILE_FOR_TRISC)
    // The next of this data-movement CPU's two scratch pages in the keep at `scratch`
    // (`used`: the pages it took), once that page's last write has left. 0: gave up.
    template <typename Ctx>
    uint32_t scratch_page(Ctx& ctx, uint32_t scratch, uint32_t& used, uint32_t where) {
        const uint32_t page = scratch +
            (2 * ctx.index + (used++ & 1u)) * kPostPageBytes;
        const bool sent = ctx.wait(
            [] {
                return ncrisc_noc_nonposted_writes_sent(noc_index);
            },
            where
        );
        if (!sent) {
            return 0;
        }
        invalidate_l1_cache();
        return page;
    }
#endif

}  // namespace post_step
