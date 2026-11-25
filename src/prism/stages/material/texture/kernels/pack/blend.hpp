// SHADE's layer blends on the pack thread, in the out pages: the masked layer's colour
// where it takes (and the merged 1/z), the glass layer's tau C + (1 - max tau) colour.
#pragma once

#include <stdint.h>

#include "vector.hpp"

namespace shade_k {

    // Words [first_word, first_word + words) of the out item at `out`: the opaque
    // layer's colour where the depth row is not 1; with `merged_depth` the merged 1/z
    // (the masked layer's where it takes, else the opaque's) to the fourth page.
    [[gnu::noinline]] inline void masked_merge(
        uint32_t out,
        const uint32_t* plane_words,
        const uint32_t* opaque_words,
        uint32_t first_word,
        uint32_t words,
        bool merged_depth,
        size_t vl
    ) {
        uint32_t* to = reinterpret_cast<uint32_t*>(out);
        if (merged_depth) {
            uint32_t* depth = to + kShadeColourPages * kPlaneWords;
            for (uint32_t at = first_word; at < first_word + words; at += 32) {
                const vbool4_t take = (__riscv_vmsne_vx_u32m8_b4(
                    __riscv_vle32_v_u32m8(
                        const_cast<const uint32_t*>(window() + at), vl
                    ),
                    0,
                    vl
                ));
                __riscv_vse32_v_u32m8(
                    depth + at,
                    __riscv_vmerge_vvm_u32m8(
                        __riscv_vle32_v_u32m8(opaque_words + at, vl),
                        __riscv_vle32_v_u32m8(plane_words + at, vl),
                        take,
                        vl
                    ),
                    vl
                );
            }
        }
        for (uint32_t at = first_word; at < first_word + words; at += 32) {
            const vbool4_t take = (__riscv_vmsne_vx_u32m8_b4(
                __riscv_vle32_v_u32m8(const_cast<const uint32_t*>(window() + at), vl),
                0,
                vl
            ));
            for (uint32_t plane = 0; plane < kShadeColourPages; ++plane) {
                uint32_t* colour = to + plane * kPlaneWords + at;
                __riscv_vse32_v_u32m8(
                    colour,
                    __riscv_vmerge_vvm_u32m8(
                        __riscv_vle32_v_u32m8(
                            opaque_words + (1 + plane) * kPlaneWords + at, vl
                        ),
                        __riscv_vle32_v_u32m8(colour, vl),
                        take,
                        vl
                    ),
                    vl
                );
            }
        }
        asm volatile("" ::: "memory");
    }

    // Glass blend (kShadeGlass) at `out`: tau C + (1 - max tau) colour where the
    // tri plane holds -2 | material (rounded as numpy), else C.
    [[gnu::noinline]] inline void glass_blend(
        uint32_t out,
        const uint32_t* opaque,
        const uint32_t* material_words,
        uint32_t first_word,
        uint32_t words,
        size_t vl
    ) {
        uint32_t* to = reinterpret_cast<uint32_t*>(out);
        for (uint32_t at = first_word; at < first_word + words; at += 32) {
            const vuint32m8_t triangle = (__riscv_vle32_v_u32m8(
                const_cast<const uint32_t*>(
                    window() + (kPlanes - 1) * kPlaneWords + at
                ),
                vl
            ));
            const vbool4_t front = __riscv_vmsgeu_vx_u32m8_b4(triangle, kMinusTwo, vl);
            const vuint32m8_t material = (__riscv_vmerge_vvm_u32m8(
                __riscv_vmv_v_x_u32m8(0, vl),
                __riscv_vand_vx_u32m8(triangle, 0xFFFF, vl),
                front,
                vl
            ));
            const vuint32m8_t row = (__riscv_vmul_vx_u32m8(
                material, 4 * kMaterialWords, vl
            ));
            const vfloat32m8_t weight = (__riscv_vluxei32_v_f32m8(
                reinterpret_cast<const float*>(material_words + kMaterialWeight),
                row,
                vl
            ));
            for (uint32_t plane = 0; plane < kShadeColourPages; ++plane) {
                uint32_t* colour = to + plane * kPlaneWords + at;
                const vfloat32m8_t behind = (__riscv_vle32_v_f32m8(
                    reinterpret_cast<const float*>(
                        opaque + (1 + plane) * kPlaneWords + at
                    ),
                    vl
                ));
                const vfloat32m8_t tau = (__riscv_vluxei32_v_f32m8(
                    reinterpret_cast<const float*>(
                        material_words + kMaterialTau + plane
                    ),
                    row,
                    vl
                ));
                const vfloat32m8_t mixed = (__riscv_vfadd_vv_f32m8(
                    __riscv_vfmul_vv_f32m8(tau, behind, vl),
                    __riscv_vfmul_vv_f32m8(
                        weight,
                        __riscv_vle32_v_f32m8(reinterpret_cast<float*>(colour), vl),
                        vl
                    ),
                    vl
                ));
                __riscv_vse32_v_f32m8(
                    reinterpret_cast<float*>(colour),
                    __riscv_vmerge_vvm_f32m8(behind, mixed, front, vl),
                    vl
                );
            }
        }
        asm volatile("" ::: "memory");
    }

}  // namespace shade_k
