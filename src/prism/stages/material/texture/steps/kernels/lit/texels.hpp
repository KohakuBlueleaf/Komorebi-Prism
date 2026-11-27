// The lit material's page passes on the pack CPU (pack/lit/texels.hpp's, its pages
// asked through the loop's request rings): a row's three keys as texel addresses, then
// kLitRows rows at a time gathered, surfaced, out.
#pragma once

#include <stdint.h>

#include "../../../../../../core/include/texel_pages/passes.hpp"
#include "../counters.hpp"
#include "../requests.hpp"
#include "surface.hpp"

namespace shade_k {

    using light_k::kLwIndex;
    using light_k::kLwRow;
    using light_k::kLwSlot;
    using light_k::kLwSlots;

    // Rows [first, end): texel addresses of the three keys (their pages asked by
    // `requests`), then kLitRows rows at a time gathered, surfaced and written out.
    inline bool lit_texels(
        const compute_mail::Waits& waits,
        const material_step::Requests& requests,
        uint32_t first,
        uint32_t end,
        uint32_t* work,
        texel_pages::Pages& pages,
        const uint32_t* table,
        uint32_t slots_address,
        uint32_t page_limit,
        bool merging,
        const Parts& parts,
        Counters& counters
    ) {
        uint32_t* values = counters.values;
        const uint32_t white = kShadeSlots * kTexPageBytes;
        const size_t vl = __riscv_vsetvl_e32m8(32);
        uint32_t* index = work + kLwIndex;
        const uint32_t* slot_offsets = work + kLwSlot;
        const uint32_t* slot_words = work + kLwSlots;
        const uint32_t* texels = reinterpret_cast<const uint32_t*>(slots_address);
        uint32_t* keys = work + kLwRow;
        auto scan = [&](uint32_t row) -> bool {
            __riscv_vse32_v_u32m8(
                keys, texel_pages::from_window(kVecDepth + row, vl), vl
            );
            __riscv_vse32_v_u32m8(
                keys + 32, texel_pages::from_window(kVecRed + row, vl), vl
            );
            __riscv_vse32_v_u32m8(
                keys + 64, texel_pages::from_window(kVecGreen + row, vl), vl
            );
            asm volatile("" ::: "memory");
            uint32_t row_texels = 0;
            for (uint32_t texture = 0; texture < 3; ++texture) {
                const int32_t found = texel_pages::row_addresses(
                    pages,
                    __riscv_vle32_v_u32m8(keys + 32 * texture, vl),
                    merging && texture == 0 ? kVecTri + row : texel_pages::kNoTags,
                    index + 1024 * texture + 32 * row,
                    page_limit,
                    white,
                    true,
                    false,
                    vl
                );
                if (found < 0) {
                    return false;
                }
                row_texels += static_cast<uint32_t>(found);
            }
            values[kShadeProfTexels] += row_texels;
            return true;
        };
        auto gather = [&](uint32_t pass_first, uint32_t pass_end) -> bool {
            const uint32_t started = km::wall();
            for (uint32_t block = pass_first; block < pass_end; block += kLitRows) {
                const uint32_t block_end = block + kLitRows < pass_end
                    ? block + kLitRows
                    : pass_end;
                for (uint32_t r = block; r < block_end; ++r) {
                    gather_row(
                        r,
                        kVecGather + kGatherVectors * (r - block),
                        index,
                        slot_offsets,
                        slot_words,
                        table,
                        texels,
                        merging,
                        vl
                    );
                }
                asm volatile("" ::: "memory");
                order(word(kVecGather + kGatherVectors * (block_end - block) - 1) + 62);
                for (uint32_t r = block; r < block_end; ++r) {
                    surface_row(kVecGather + kGatherVectors * (r - block));
                }
                tensix_sync();
                for (uint32_t r = block; r < block_end; ++r) {
                    surface_out(
                        r,
                        kVecGather + kGatherVectors * (r - block),
                        parts,
                        slot_offsets,
                        slot_words,
                        vl
                    );
                }
                asm volatile("" ::: "memory");
            }
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
