// An output block of a step (post, depth_out): on the pack CPU a band's rows of planes
// copied into the payload of an output block (the loop's out_reserve, out_push) for
// the tile's page; on a data-movement CPU the payload converted through this CPU's
// scratch page and copied back over it (the loop writes it from the payload).
#pragma once

#include <stdint.h>

#include "../../../../../program/frame/kernels/frame.h"
#include "post_step.h"

#if defined(COMPILE_FOR_TRISC)
#include "../../../../../program/frame/kernels/pack.hpp"
#include "../../../../raster/kernels/common/layouts.hpp"
#if defined(TRISC_PACK)
#include <riscv_vector.h>
#endif
#else
#include "api/dataflow/dataflow_api.h"
#include "komorebi/device/km_worker.hpp"
#include "../../../../raster/kernels/common/layouts.hpp"
#endif

namespace post_step {

    static_assert(kPostHeaderBytes == FO_HEADER_BYTES);

#if defined(TRISC_PACK)
    // `planes` planes from L1 `from` (a page each), the row pairs of the tile's rows,
    // into a block of output `output` for the tile's page `page` (below `pages`),
    // pushed: the rows' bytes from their byte in the page. False: gave up (recorded at
    // `where`).
    template <typename Ctx, typename Tile>
    bool push_planes(
        Ctx& ctx,
        uint32_t output,
        uint32_t where,
        const Tile& tile,
        uint32_t from,
        uint32_t planes,
        uint32_t pages
    ) {
        const compute_mail::Stops stops = {
            ctx.compute.control(),
            fill_k::kGaveWait,
            fill_k::kGaveBadItem,
            where,
            where,
            where
        };
        if (tile.page >= pages || !(tile.first_row < tile.end_row) ||
            tile.end_row > 32) {
            compute_mail::stop(stops, stops.gave_bad, where);
            return false;
        }
        const uint32_t block = prism_frame::out_reserve(ctx, output);
        if (block == 0) {
            return false;
        }
        const uint32_t payload = block + FO_HEADER_BYTES;
        // two rows of a plane are 256 contiguous bytes (raster.h kRowBytes)
        const uint32_t first_word = (tile.first_row & ~1u) * fill_k::kRowBytes / 4;
        const uint32_t end_word = ((tile.end_row + 1) & ~1u) * fill_k::kRowBytes / 4;
        const size_t vl = __riscv_vsetvl_e32m8(32);
        for (uint32_t plane = 0; plane < planes; ++plane) {
            const uint32_t* source = reinterpret_cast<const uint32_t*>(
                from + plane * kPostPageBytes
            );
            uint32_t* target = reinterpret_cast<uint32_t*>(
                payload + plane * kPostPageBytes
            );
            for (uint32_t i = first_word; i < end_word; i += 32) {
                __riscv_vse32_v_u32m8(
                    target + i, __riscv_vle32_v_u32m8(source + i, vl), vl
                );
            }
        }
        asm volatile("fence" ::: "memory");
        prism_frame::out_push(
            ctx,
            output,
            block,
            tile.page,
            tile.first_row * fill_k::kRowBytes,
            (tile.end_row - tile.first_row) * fill_k::kRowBytes,
            kPostPageBytes
        );
        return true;
    }
#endif

#if !defined(COMPILE_FOR_TRISC)
    // The rows [first_row, end_row) of the block whose payload is at `payload` (from
    // its header: the rows' byte in the page and their `bytes`).
    inline void rows_of(
        uint32_t payload, uint32_t bytes, uint32_t& first_row, uint32_t& end_row
    ) {
        const volatile tt_l1_ptr uint32_t* header = km::l1(payload - FO_HEADER_BYTES);
        first_row = header[FO_OFFSET] / fill_k::kRowBytes;
        end_row = first_row + bytes / fill_k::kRowBytes;
    }

    // This data-movement CPU's scratch page in the keep at `scratch`.
    inline uint32_t scratch_page(uint32_t scratch) {
        return scratch + (km::kMover == km::kMoverA ? 0 : kPostPageBytes);
    }

    // `bytes` from L1 `from` back over the payload at `payload`; the bytes.
    inline uint32_t copy_back(uint32_t from, uint32_t payload, uint32_t bytes) {
        const tt_l1_ptr uint32_t* source = reinterpret_cast<const tt_l1_ptr uint32_t*>(
            from
        );
        tt_l1_ptr uint32_t* target = reinterpret_cast<tt_l1_ptr uint32_t*>(payload);
        for (uint32_t i = 0; i < bytes / 4; ++i) {
            target[i] = source[i];
        }
        return bytes;
    }
#endif

}  // namespace post_step
