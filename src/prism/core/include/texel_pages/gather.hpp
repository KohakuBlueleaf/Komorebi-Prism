// The pack thread's gather from the slots (SHADE, LIGHT): texels at row_addresses'
// addresses, the mask's tagged ones, a channel's byte decoded by a table into Dst.
#pragma once

#include <stdint.h>

#include "pages.hpp"

namespace texel_pages {

    // The texels at `address` (byte offsets into the slots).
    inline vuint32m8_t texels(const uint32_t* slots, vuint32m8_t address, size_t vl) {
        return __riscv_vluxei32_v_u32m8(slots, address, vl);
    }

    // A tagged address (row_addresses with tags) without the mask's slot.
    inline vuint32m8_t untagged(vuint32m8_t address, size_t vl) {
        return __riscv_vand_vx_u32m8(address, (1u << kMaskSlotShift) - 1, vl);
    }

    // The mask's texel address of a tagged address: the same place in the mask's
    // slot, else (no tag) the albedo's.
    inline vuint32m8_t mask_address(vuint32m8_t address, size_t vl) {
        const vuint32m8_t mask_slot = __riscv_vsrl_vx_u32m8(
            address, kMaskSlotShift, vl
        );
        return __riscv_vmerge_vvm_u32m8(
            untagged(address, vl),
            __riscv_vor_vv_u32m8(
                __riscv_vsll_vx_u32m8(__riscv_vsub_vx_u32m8(mask_slot, 1, vl), 12, vl),
                __riscv_vand_vx_u32m8(address, kTexPageBytes - 1, vl),
                vl
            ),
            __riscv_vmsne_vx_u32m8_b4(mask_slot, 0, vl),
            vl
        );
    }

    // Byte `channel` of each texel through the 256-word `table` to Dst vector `vector`.
    inline void decode_to(
        const uint32_t* table,
        vuint32m8_t texel,
        uint32_t channel,
        uint32_t vector,
        size_t vl
    ) {
        const vuint32m8_t byte = (__riscv_vand_vx_u32m8(
            __riscv_vsrl_vx_u32m8(texel, 8 * channel, vl), 0xFF, vl
        ));
        to_window(
            vector,
            __riscv_vluxei32_v_u32m8(table, __riscv_vsll_vx_u32m8(byte, 2, vl), vl),
            vl
        );
    }

}  // namespace texel_pages
