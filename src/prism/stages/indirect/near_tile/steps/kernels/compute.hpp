// The near tile step on the compute CPUs. The pack CPU asks the tile's table into the
// plane (every CPU reads it once marked), then for
// each of its row blocks the block's W tiles and its operands S (the unpack CPU serving
// the asks' mails); the matrix engine makes the block's E = sum_k W_k . S_k: unpack and
// math the product, pack E's tile into its ring and from there the three channels of
// its rows into their places of the plane near.light, marked on (or marked off).
#pragma once

#include <stdint.h>

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
    // The table of tile `tile` asked into the plane (its count 0 when the ask gave up),
    // the plane's E zeroed, its half rows and columns and the upsample's tensor
    // written, then `seq` at kNearSeq. False: gave up.
    template <typename Ctx, typename Tile>
    bool near_table(Ctx& ctx, const Tile& tile, uint32_t plane, uint32_t seq) {
        const uint32_t t = plane + 4 * kNearTableAt;
        bool served = false;
        const uint32_t ask = prism_frame::ask_begin(
            ctx, ctx.page[PRISM_TF_NEAR_TILE_TABLE], kNearTableBytes
        );
        if (ask != 0) {
            prism_frame::ask_entry(ask, 0, tile.tile, t);
            served = prism_frame::ask_wait(ctx, prism_frame::ask_post(ctx, ask, 1));
        }
        if (!served) {
            reinterpret_cast<volatile uint32_t*>(t)[0] = 0;
        }
        volatile uint32_t* words = reinterpret_cast<volatile uint32_t*>(plane);
        for (uint32_t i = 0; i < kNearWords; ++i) {
            words[i] = 0;
        }
        const uint32_t across = grid_of(ctx.page[TF_GRID]).across;
        const uint32_t half = ctx.page[PRISM_TF_NEAR_TILE_HALF];
        const uint32_t cols = half >> kNearHalfShift, rows = half & 0xFFFF;
        const uint32_t x0 = kHalfTile * (tile.tile % across);
        const uint32_t y0 = kHalfTile * (tile.tile / across);
        words[kNearRows] = rows - y0 < kNearSide ? rows - y0 : kNearSide;
        words[kNearCols] = cols - x0 < kNearSide ? cols - x0 : kNearSide;
        words[kNearUpsample] = ctx.page[PRISM_TF_NEAR_TILE_UPSAMPLE];
        asm volatile("fence" ::: "memory");
        words[kNearSeq] = seq;
        return served;
    }

    // The block at `entry`: its W tiles and its operands asked into their rings
    // (reserved and pushed kNearMostOperands each, also when an ask gave up). False:
    // gave up.
    template <typename Ctx>
    bool near_asks(Ctx& ctx, const uint32_t* entry, bool first) {
        const compute_mail::Waits waits = waits_of(ctx.compute.control());
        if (!compute_mail::reserve(waits, kW, kNearMostOperands) ||
            !compute_mail::reserve(waits, kS, kNearMostOperands)) {
            return false;
        }
        const uint32_t count = entry[0];
        const uint32_t w = compute_mail::write_ptr(kW);
        const uint32_t s = compute_mail::write_ptr(kS);
        bool served = count <= kNearMostOperands;
        const uint32_t ask_w = prism_frame::ask_begin(
            ctx, ctx.page[PRISM_TF_NEAR_TILE_WEIGHTS], kNearWTileBytes
        );
        uint32_t half_w = 2;
        if (ask_w != 0 && served) {
            for (uint32_t k = 0; k < count; ++k) {
                prism_frame::ask_entry(ask_w, k, entry[1] + k, w + k * kNearWTileBytes);
            }
            half_w = prism_frame::ask_post(ctx, ask_w, count);
        }
        const uint32_t ask_s = prism_frame::ask_begin(
            ctx, ctx.page[PRISM_TF_NEAR_TILE_OPERAND], kNearSTileBytes
        );
        uint32_t half_s = 2;
        if (ask_s != 0 && served) {
            for (uint32_t k = 0; k < count; ++k) {
                const uint32_t pair = entry[2 + k / 2];
                prism_frame::ask_entry(
                    ask_s,
                    k,
                    (k & 1) ? pair >> 16 : pair & 0xFFFF,
                    s + k * kNearSTileBytes
                );
            }
            half_s = prism_frame::ask_post(ctx, ask_s, count);
        }
        served = served && half_w <= 1 && prism_frame::ask_wait(ctx, half_w);
        served = served && half_s <= 1 && prism_frame::ask_wait(ctx, half_s);
        if (first) {  // Dst zero before the products accumulate into it
            TTI_ZEROACC(p_zeroacc::CLR_ALL, 1 /*fp32*/, 0, ADDR_MOD_1, 0);
            tensix_sync();
        }
        compute_mail::push(
            kW, w + kNearMostOperands * kNearWTileBytes - 4, kNearMostOperands
        );
        compute_mail::push(
            kS, s + kNearMostOperands * kNearSTileBytes - 4, kNearMostOperands
        );
        return served;
    }

    // E's block tile (packed: faces of 16 x 16, rows the block's 32 rows, columns the
    // channels) into the plane: row r's three channels added at its place, if any.
    inline void near_copy(uint32_t e, uint32_t plane, const uint32_t* places) {
        const float* from = reinterpret_cast<const float*>(e);
        float* to = reinterpret_cast<float*>(plane);
        for (uint32_t r = 0; r < 32; ++r) {
            const uint32_t place = (places[r / 2] >> (16 * (r & 1))) & 0xFFFF;
            if (place == kNearSkip) {
                continue;
            }
            const float* row = from + 512 * (r >> 4) + 16 * (r & 15);
            for (uint32_t channel = 0; channel < 3; ++channel) {
                to[kNearSide * kNearSide * channel + place] += row[channel];
            }
        }
    }
#endif

    // The table in the plane once the pack CPU marked it with `seq` (its words).
    inline const uint32_t* near_table_words(uint32_t plane, uint32_t seq) {
        volatile uint32_t* words = reinterpret_cast<volatile uint32_t*>(plane);
        while (words[kNearSeq] != seq) {
        }
        asm volatile("" ::: "memory");
        return reinterpret_cast<const uint32_t*>(plane) + kNearTableAt;
    }

    // The product of the block at `entry` on the three CPUs: the sum over its operands
    // k of W's tile k times S's tile k, into E's tile (and on pack, the plane).
    inline void near_product(uint32_t plane, const uint32_t* entry) {
        const uint32_t count = entry[0];
        cb_wait_front(kW, kNearMostOperands);
        cb_wait_front(kS, kNearMostOperands);
        tile_regs_acquire();
        for (uint32_t k = 0; k < count && k < kNearMostOperands; ++k) {
            matmul_block(kW, kS, k, k, 0, 0, 1, 1, 1);
        }
        tile_regs_commit();
        tile_regs_wait();
        pack_tile<true>(0, kE, 0);
        tile_regs_release();
#if defined(TRISC_PACK)
        // E's tile in L1: the packer done, then this thread's instructions
        TTI_STALLWAIT(p_stall::STALL_TDMA | p_stall::STALL_THCON, p_stall::PACK);
        tensix_sync();
        near_copy(compute_mail::write_ptr(kE), plane, entry + kNearEntryPlaces);
#else
        static_cast<void>(plane);
#endif
        cb_pop_front(kW, kNearMostOperands);
        cb_pop_front(kS, kNearMostOperands);
    }

}  // namespace near_tile_step

// The near tile step on a compute CPU (all three call it): the pack CPU's table and
// asks (the unpack CPU serving their mails), then each row block's product. False:
// gave up (recorded).
template <typename Ctx, typename Tile, typename Planes>
bool near_tile_compute(Ctx& ctx, const Tile& tile, Planes& planes) {
    using namespace near_tile_step;
    const uint32_t plane = planes.near_light;
    const bool on = ctx.page[PRISM_TF_NEAR_TILE_ON] != 0;
    bool asked = true;
#if defined(TRISC_PACK)
    volatile uint32_t* words = reinterpret_cast<volatile uint32_t*>(plane);
    words[kNearOn] = 0;
#else
    static_cast<void>(tile);
#endif
    if (!on) {
        return true;
    }
    static uint32_t tiles = 0;  // this CPU's tiles with the product on
    const uint32_t seq = ++tiles;
#if defined(TRISC_PACK)
    asked = near_table(ctx, tile, plane, seq);
    compute_mail::end_mails();
#elif defined(TRISC_UNPACK)
    compute_mail::serve_mails(waits_of(ctx.compute.control()));
#endif
    const uint32_t* table = near_table_words(plane, seq);
    const uint32_t blocks = table[0];
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
#endif
    for (uint32_t b = 0; b < blocks; ++b) {
        const uint32_t* entry = table + 1 + kNearEntryWords * b;
#if defined(TRISC_PACK)
        asked = near_asks(ctx, entry, b == 0) && asked;
        compute_mail::end_mails();
#elif defined(TRISC_UNPACK)
        compute_mail::serve_mails(waits_of(ctx.compute.control()));
#endif
        near_product(plane, entry);
    }
#if defined(TRISC_PACK)
    words[kNearOn] = asked ? 1 : 0;
    return asked;
#else
    static_cast<void>(asked);
    return true;
#endif
}
