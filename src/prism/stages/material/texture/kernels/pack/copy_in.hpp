// SHADE's copy-in on the pack thread: an item's rows of its five planes into Dst; when
// merging, the triangle -1 where the opaque layer's pixel is as near or nearer.
#pragma once

#include <stdint.h>

#include "vector.hpp"

namespace shade_k {

    // The opaque layer's five pages after the item's in the planes' ring (the reader's
    // second five).
    inline uint32_t opaque_after(uint32_t planes) {
        uint32_t opaque = planes + kPlanes * kOutPageBytes;
        if (opaque >= get_local_cb_interface(kFieldInPlanes).fifo_limit << 4) {
            opaque -= get_local_cb_interface(kFieldInPlanes).fifo_size << 4;
        }
        return opaque;
    }

    // Rows [first_row, end_row) of the planes at `plane_words` into Dst (two rows: 64
    // words); merging, triangle -1 unless nearer than `opaque_words`' (1/z as unsigned
    // bits, a tie to it).
    [[gnu::noinline]] inline void copy_in(
        const uint32_t* plane_words,
        const uint32_t* opaque_words,
        int32_t first_row,
        int32_t end_row,
        bool merging,
        size_t vl
    ) {
        for (uint32_t plane = 0; plane < kPlanes; ++plane) {
            for (int32_t pair = first_row / 2; pair < end_row / 2; ++pair) {
                const uint32_t at = plane * kPlaneWords + 64 * pair;
                for (uint32_t half = 0; half < 64; half += 32) {
                    vuint32m8_t value = (__riscv_vle32_v_u32m8(
                        plane_words + at + half, vl
                    ));
                    if (merging && plane == kPlanes - 1) {
                        const uint32_t depth_at = 64 * pair + half;
                        const vbool4_t nearer = (__riscv_vmand_mm_b4(
                            __riscv_vmsltu_vx_u32m8_b4(value, 0x80000000, vl),
                            __riscv_vmsgtu_vv_u32m8_b4(
                                __riscv_vle32_v_u32m8(plane_words + depth_at, vl),
                                __riscv_vle32_v_u32m8(opaque_words + depth_at, vl),
                                vl
                            ),
                            vl
                        ));
                        value = (__riscv_vmerge_vvm_u32m8(
                            __riscv_vmv_v_x_u32m8(kMinusOne, vl), value, nearer, vl
                        ));
                    }
                    __riscv_vse32_v_u32m8(
                        const_cast<uint32_t*>(window() + at + half), value, vl
                    );
                }
            }
        }
        asm volatile("" ::: "memory");
        order((kPlanes - 1) * kPlaneWords + 32 * end_row - 1);
    }

}  // namespace shade_k
