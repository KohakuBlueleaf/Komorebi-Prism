// The near tile step on the compute CPUs. The pack CPU asks the tile's record of W_T
// and its S_T (the unpack CPU serving the asks' mails), then the matrix engine makes E
// = W_T . S_T a record tile at a time: unpack and math the product, pack E's tile into
// its ring and from there the three channels' columns into the plane near.light, marked
// on (or marked off).
#pragma once

#include <stdint.h>

#include <riscv_vector.h>

#include "api/compute/matmul.h"
#include "api/compute/reconfig_data_format.h"

#include "../../../../../core/include/compute_mail.hpp"
#include "../../../../../core/include/grid.h"
#include "../../../../../core/include/thread/frame.h"
#include "../../../../../core/include/thread/record.h"
#include "../../../../../program/frame/kernels/pack.hpp"
#include "near_tile_step.h"

namespace near_tile_step {

    constexpr uint32_t kW = kFieldNearTileW;
    constexpr uint32_t kS = kFieldNearTileS;
    constexpr uint32_t kE = kFieldNearTileE;

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
    // One ask of `count` pages of `page_bytes` from the tensor at `base`, page
    // `first` + i into L1 `to` + i x page_bytes: the half that serves it, or 2 (gave
    // up).
    template <typename Ctx>
    uint32_t ask_pages(
        Ctx& ctx,
        uint32_t base,
        uint32_t page_bytes,
        uint32_t first,
        uint32_t count,
        uint32_t to
    ) {
        const uint32_t ask = prism_frame::ask_begin(ctx, base, page_bytes);
        if (ask == 0) {
            return 2;
        }
        for (uint32_t i = 0; i < count; ++i) {
            prism_frame::ask_entry(ask, i, first + i, to + i * page_bytes);
        }
        return prism_frame::ask_post(ctx, ask, count);
    }

    // Half `part` of the tile's record asked into its ring (with the first: the
    // operand into its ring; the tile's half rows and columns and the upsample's
    // tensor into the plane), pushed once reserved. False: gave up.
    template <typename Ctx, typename Tile>
    bool near_asks(Ctx& ctx, const Tile& tile, uint32_t plane, uint32_t part) {
        const compute_mail::Waits waits = waits_of(ctx.compute.control());
        const bool first = part == 0;
        if (!compute_mail::reserve(waits, kW, kNearPartTiles) ||
            (first && !compute_mail::reserve(waits, kS, 1))) {
            return false;
        }
        const uint32_t w = compute_mail::write_ptr(kW);
        const uint32_t s = compute_mail::write_ptr(kS);
        uint32_t halves[2] = {
            ask_pages(
                ctx,
                ctx.page[PRISM_TF_NEAR_TILE_WEIGHTS],
                kNearWTileBytes,
                kNearRecordTiles * tile.tile + kNearPartTiles * part,
                kNearPartTiles,
                w
            ),
            2
        };
        if (first) {
            halves[1] = ask_pages(
                ctx,
                ctx.page[PRISM_TF_NEAR_TILE_OPERAND],
                kNearSTileBytes,
                tile.tile,
                1,
                s
            );
        }
        bool served = true;
        for (uint32_t i = 0; i < (first ? 2u : 1u); ++i) {
            served = served && halves[i] <= 1 && prism_frame::ask_wait(ctx, halves[i]);
        }
        if (first) {  // Dst zero before the products accumulate into it
            TTI_ZEROACC(p_zeroacc::CLR_ALL, 1 /*fp32*/, 0, ADDR_MOD_1, 0);
            tensix_sync();
        }
        // pushed even when an ask gave up: the unpack CPU's product then ends
        compute_mail::push(
            kW, w + kNearPartTiles * kNearWTileBytes - 4, kNearPartTiles
        );
        if (first) {
            compute_mail::push(kS, s + kNearSTileBytes - 4, 1);
        }
        if (!served || !first) {
            return served;
        }
        const uint32_t across = grid_of(ctx.page[TF_GRID]).across;
        const uint32_t half = ctx.page[PRISM_TF_NEAR_TILE_HALF];
        const uint32_t cols = half >> kNearHalfShift, rows = half & 0xFFFF;
        const uint32_t x0 = kHalfTile * (tile.tile % across);
        const uint32_t y0 = kHalfTile * (tile.tile / across);
        volatile uint32_t* words = reinterpret_cast<volatile uint32_t*>(plane);
        words[kNearRows] = rows - y0 < kHalfTile ? rows - y0 : kHalfTile;
        words[kNearCols] = cols - x0 < kHalfTile ? cols - x0 : kHalfTile;
        words[kNearUpsample] = ctx.page[PRISM_TF_NEAR_TILE_UPSAMPLE];
        return true;
    }

    // E's record tile k (packed: faces of 16 x 16, rows its 32 half pixels, columns the
    // channels) into the plane: half rows 2k and 2k + 1, a channel after another.
    inline void near_copy(uint32_t e, uint32_t plane, uint32_t k) {
        constexpr size_t vl = kHalfTile;
        const float* from = reinterpret_cast<const float*>(e);
        float* to = reinterpret_cast<float*>(plane);
        for (uint32_t odd = 0; odd < 2; ++odd) {
            for (uint32_t channel = 0; channel < 3; ++channel) {
                const vfloat32m4_t row = __riscv_vlse32_v_f32m4(
                    from + 512 * odd + channel, 4 * kHalfTile, vl
                );
                __riscv_vse32_v_f32m4(
                    to + kHalfTile * kHalfTile * channel + kHalfTile * (2 * k + odd),
                    row,
                    vl
                );
            }
        }
    }
#endif

    // The product of half `part` on the three CPUs: E's record tiles kNearPartTiles x
    // part on, each W's tile k times S (S freed after the last half).
    inline void near_product(uint32_t plane, uint32_t part) {
        cb_wait_front(kW, kNearPartTiles);
        cb_wait_front(kS, 1);
        reconfig_data_format(kS, kW);
        matmul_block_init(kW, kS, 0, 1, 1, 1);
#if defined(TRISC_PACK)
        _llk_pack_reconfig_data_format_<DST_ACCUM_MODE>(
            pack_src_format[kE],
            pack_dst_format[kE],
            get_local_cb_interface(kE).fifo_page_size,
            pack_tile_c_dim[kE],
            pack_tile_num_faces[kE],
            false
        );
        const uint32_t e = compute_mail::write_ptr(kE);
#endif
        for (uint32_t k = 0; k < kNearPartTiles; ++k) {
            tile_regs_acquire();
            matmul_block(kW, kS, k, 0, 0, 0, 1, 1, 1);
            tile_regs_commit();
            tile_regs_wait();
            pack_tile<true>(0, kE, 0);
            tile_regs_release();
#if defined(TRISC_PACK)
            // E's tile in L1: the packer done, then this thread's instructions
            TTI_STALLWAIT(p_stall::STALL_TDMA | p_stall::STALL_THCON, p_stall::PACK);
            tensix_sync();
            near_copy(e, plane, kNearPartTiles * part + k);
#endif
        }
        cb_pop_front(kW, kNearPartTiles);
        if (part + 1 == kNearParts) {
            cb_pop_front(kS, 1);
        }
#if !defined(TRISC_PACK)
        static_cast<void>(plane);
#endif
    }

}  // namespace near_tile_step

// The near tile step on a compute CPU (all three call it), the record in halves: the
// pack CPU's asks (the unpack CPU serving their mails), then the product. False: gave
// up (recorded).
template <typename Ctx, typename Tile, typename Planes>
bool near_tile_compute(Ctx& ctx, const Tile& tile, Planes& planes) {
    const uint32_t plane = planes.near_light;
    const bool on = ctx.page[PRISM_TF_NEAR_TILE_ON] != 0;
    bool asked = true;
#if defined(TRISC_PACK)
    volatile uint32_t* words = reinterpret_cast<volatile uint32_t*>(plane);
    words[near_tile_step::kNearOn] = 0;
#else
    static_cast<void>(tile);
#endif
    for (uint32_t part = 0; part < (on ? near_tile_step::kNearParts : 1u); ++part) {
#if defined(TRISC_PACK)
        asked = (!on || near_tile_step::near_asks(ctx, tile, plane, part)) && asked;
        compute_mail::end_mails();
#elif defined(TRISC_UNPACK)
        compute_mail::serve_mails(near_tile_step::waits_of(ctx.compute.control()));
#endif
        if (on) {
            near_tile_step::near_product(plane, part);
        }
    }
#if defined(TRISC_PACK)
    words[near_tile_step::kNearOn] = on && asked ? 1 : 0;
    return asked;
#else
    static_cast<void>(asked);
    return true;
#endif
}
