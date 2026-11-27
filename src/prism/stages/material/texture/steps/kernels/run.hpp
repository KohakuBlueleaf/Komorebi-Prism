// The material step's state of one tile thread on the pack CPU: its waits, the table,
// the band's rows, the page cache, the page passes' space, its requests, its counters.
#pragma once

#include <stdint.h>

#include "../../kernels/pack/keys.hpp"
#include "counters.hpp"
#include "order.hpp"
#include "requests.hpp"

namespace material_step {

    // The material work's words (kShadeWorkBytes): the texel addresses, the page
    // passes' table, a row's keys (texels.hpp: after the table's used slots), a pass's
    // ask list.
    constexpr uint32_t kWorkIndex = 0;     // 1,024 texel addresses, row by row
    constexpr uint32_t kWorkPages = 1024;  // texel_pages::Pages (2 hash sizes + slots)
    constexpr uint32_t kRowKeys = 32;      // a row's keys
    constexpr uint32_t
        kWorkAsked = (kWorkPages + 2 * kPagesHashSize + kShadeSlots + kRowKeys);
    static_assert(4 * (kWorkAsked + 1 + kShadeSlots) <= kShadeWorkBytes);

    // The page cache's bytes: kShadeSlots pages and the white texel's.
    constexpr uint32_t kCacheBytes = (kShadeSlots + 1) * kTexPageBytes;

    // The step's keep `run`: the pack CPU's Run of a tile thread, then its Order, then
    // the ListStream of the layer it shades (material.hpp).
    constexpr uint32_t kRunBytes = 512;

    // The pack CPU's state of one tile thread.
    struct Run {
        compute_mail::Waits waits;
        Table table;
        int32_t first_row = 0, end_row = 0;
        uint32_t tile_y = 0, first_word = 0, words = 0;
        uint32_t slots_address = 0;  // the page cache
        uint32_t* index = nullptr;   // 1,024 texel addresses, row by row
        texel_pages::Pages pages;
        Requests requests;
        Counters counters;
        size_t vl = 0;

        // Tile `tile` of the command whose context is `ctx`: the table at `table_at`,
        // the material work at `work`, the page cache at `cache`, the textures' tensor
        // `textures`; false: the table is not one (recorded).
        template <typename Tile>
        bool start(
            prism_frame::ComputeContext& ctx,
            const Tile& tile,
            uint32_t table_at,
            uint32_t work,
            uint32_t cache,
            uint32_t textures
        ) {
            waits = waits_of(ctx.compute.control());
            first_row = static_cast<int32_t>(tile.first_row);
            end_row = static_cast<int32_t>(tile.end_row);
            tile_y = tile.tile / grid_of(ctx.page[TF_GRID]).across;
            first_word = kRowBytes / 4 * tile.first_row;
            words = kRowBytes / 4 * (tile.end_row - tile.first_row);
            vl = __riscv_vsetvl_e32m8(32);
            slots_address = cache;
            *reinterpret_cast<volatile uint32_t*>(
                slots_address + kShadeSlots * kTexPageBytes
            ) = 0xFFFFFFFF;  // the white texel: albedo 1
            uint32_t* words_at = reinterpret_cast<uint32_t*>(work);
            index = words_at + kWorkIndex;
            pages.place(words_at + kWorkPages);
            requests = {&ctx, textures, cache, words_at + kWorkAsked};
            if (table.at(table_at)) {
                return true;
            }
            compute_mail::stop(waits.stops, kGaveBadItem, kWhereShadeBad);
            return false;
        }
    };

    static_assert(sizeof(Run) <= kRunBytes && alignof(Run) <= 4);

}  // namespace material_step
