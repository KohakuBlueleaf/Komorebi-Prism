// The material step's page passes and gather on the pack CPU (pack/texels.hpp's, its
// pages asked through the loop's request rings): a row's keys as texel addresses, its
// pages asked, the texels' linear rgb to Dst.
#pragma once

#include <stdint.h>

#include "../../../../../core/include/texel_pages/gather.hpp"
#include "../../../../../core/include/texel_pages/passes.hpp"
#include "counters.hpp"
#include "requests.hpp"

namespace shade_k {

    // Merging: where the alpha byte is opaque on a pixel not FILL's empty, the depth
    // row 1 (the masked layer takes it), else 0.
    inline void take_row(
        const uint32_t* slots, vuint32m8_t address, uint32_t r, size_t vl
    ) {
        const vuint32m8_t alpha_texel = texel_pages::texels(
            slots, texel_pages::mask_address(address, vl), vl
        );
        const vuint32m8_t triangle = texel_pages::from_window(kVecTri + r, vl);
        const vbool4_t take = (__riscv_vmand_mm_b4(
            __riscv_vmsgeu_vx_u32m8_b4(alpha_texel, kAlphaOpaque << 24, vl),
            __riscv_vmsne_vx_u32m8_b4(triangle, kMinusOne, vl),
            vl
        ));
        texel_pages::to_window(
            kVecDepth + r,
            __riscv_vmerge_vxm_u32m8(__riscv_vmv_v_x_u32m8(0, vl), 1, take, vl),
            vl
        );
    }

    // Rows [first, end): texel offsets from the keys, in passes whose pages fit the
    // cache (asked by `requests`), texels to albedo rows; merging also the mask's,
    // depth row 1 where it takes.
    [[gnu::noinline]] inline bool texels(
        const compute_mail::Waits& waits,
        const material_step::Requests& requests,
        uint32_t first,
        uint32_t end,
        uint32_t* index,
        texel_pages::Pages& pages,
        const uint32_t* gamma,
        uint32_t slots_address,
        uint32_t page_limit,
        bool merging,
        Counters& counters
    ) {
        uint32_t* values = counters.values;
        const uint32_t white = kShadeSlots * kTexPageBytes;
        const size_t vl = __riscv_vsetvl_e32m8(32);
        const uint32_t* slots = reinterpret_cast<const uint32_t*>(slots_address);
        // a row's texel addresses; false when its pages do not fit
        uint32_t* keys = pages.used + kShadeSlots;  // a row's keys
        auto scan = [&](uint32_t row) -> bool {
            __riscv_vse32_v_u32m8(
                keys, texel_pages::from_window(kVecDepth + row, vl), vl
            );
            asm volatile("" ::: "memory");
            const int32_t row_texels = (texel_pages::row_addresses(
                pages,
                __riscv_vle32_v_u32m8(keys, vl),
                merging ? kVecTri + row : texel_pages::kNoTags,
                index + 32 * row,
                page_limit,
                white,
                true,
                false,
                vl
            ));
            if (row_texels < 0) {
                return false;
            }
            values[kShadeProfTexels] += static_cast<uint32_t>(row_texels);
            return true;
        };
        auto gather = [&](uint32_t pass_first, uint32_t pass_end) -> bool {
            const uint32_t started = km::wall();
            for (uint32_t r = pass_first; r < pass_end; ++r) {
                const vuint32m8_t address = __riscv_vle32_v_u32m8(index + 32 * r, vl);
                const vuint32m8_t texel = texel_pages::texels(
                    slots, merging ? texel_pages::untagged(address, vl) : address, vl
                );
                if (merging) {
                    take_row(slots, address, r, vl);
                }
                for (uint32_t channel = 0; channel < 3; ++channel) {
                    texel_pages::decode_to(
                        gamma, texel, channel, kVecAlbedo + 32 * channel + r, vl
                    );
                }
            }
            asm volatile("" ::: "memory");
            values[kShadeProfGather] += km::wall() - started;
            return true;
        };
        texel_pages::PassCounts counts;
        const bool served = material_step::request_passes(
            waits, requests, first, end, pages, counts, scan, gather
        );
        add_counts(counters, counts);
        return served;
    }

}  // namespace shade_k
