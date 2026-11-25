// LIGHT on the pack CPU, glass form: where the glass layer is in front, its
// weighted albedo and tau C into Dst.
#pragma once

#include <stdint.h>

#include "dst.hpp"

namespace light_k {

    // Glass, `quarter`'s rows: in front (bit 31 clear, 1/z above the merged; a tie
    // behind) the glass word, else bit 31; (1 - max tau) a; tau C. True if any.
    __attribute__((noinline)) bool glass_in(
        uint32_t planes,
        uint32_t quarter,
        const uint32_t* material_words,
        uint32_t limit,
        uint32_t size,
        size_t vl
    ) {
        constexpr uint32_t kWords = 32 * kLightRows;
        auto page_of = [&](uint32_t plane) -> const uint32_t* {
            uint32_t page = planes + plane * kOutPageBytes;
            if (page >= limit) {
                page -= size;
            }
            return reinterpret_cast<const uint32_t*>(page) + kWords * quarter;
        };
        const uint32_t* glass_material = page_of(kLightItemPlanes - 1);
        const uint32_t* glass_depth = page_of(kLightItemPlanes - 2);
        const uint32_t* depth = page_of(kLightGlassDepth);
        uint32_t fronts = 0;
        for (uint32_t i = 0; i < kWords; i += 32) {
            const vuint32m8_t material = __riscv_vle32_v_u32m8(glass_material + i, vl);
            const vbool4_t front = (__riscv_vmand_mm_b4(
                __riscv_vmsltu_vx_u32m8_b4(material, kMaterialNone, vl),
                __riscv_vmsgtu_vv_u32m8_b4(
                    __riscv_vle32_v_u32m8(glass_depth + i, vl),
                    __riscv_vle32_v_u32m8(depth + i, vl),
                    vl
                ),
                vl
            ));
            fronts += __riscv_vcpop_m_b4(front, vl);
            __riscv_vse32_v_u32m8(
                const_cast<uint32_t*>(window() + kWords * kLvMaterial + i),
                __riscv_vmerge_vvm_u32m8(
                    __riscv_vmv_v_x_u32m8(0xFFFFFFFF, vl), material, front, vl
                ),
                vl
            );
            const vuint32m8_t row = (__riscv_vmul_vx_u32m8(
                __riscv_vmerge_vvm_u32m8(
                    __riscv_vmv_v_x_u32m8(0, vl),
                    __riscv_vand_vx_u32m8(material, 0xFFFF, vl),
                    front,
                    vl
                ),
                4 * kMaterialWords,
                vl
            ));
            const vfloat32m8_t weight = (__riscv_vluxei32_v_f32m8(
                reinterpret_cast<const float*>(material_words + kMaterialWeight),
                row,
                vl
            ));
            for (uint32_t channel = 0; channel < 3; ++channel) {
                const vfloat32m8_t albedo = (__riscv_vle32_v_f32m8(
                    reinterpret_cast<const float*>(page_of(channel) + i), vl
                ));
                __riscv_vse32_v_f32m8(
                    reinterpret_cast<float*>(const_cast<uint32_t*>(
                        window() + kWords * (kLvAlbedo + channel) + i
                    )),
                    __riscv_vfmul_vv_f32m8(weight, albedo, vl),
                    vl
                );
                const vfloat32m8_t behind = (__riscv_vle32_v_f32m8(
                    reinterpret_cast<const float*>(page_of(kLightGlassC + channel) + i),
                    vl
                ));
                const vfloat32m8_t tau = (__riscv_vluxei32_v_f32m8(
                    reinterpret_cast<const float*>(
                        material_words + kMaterialTau + channel
                    ),
                    row,
                    vl
                ));
                __riscv_vse32_v_f32m8(
                    reinterpret_cast<float*>(const_cast<uint32_t*>(
                        window() + 64 * (kLvC / 2) + kWords * channel + i
                    )),
                    __riscv_vmerge_vvm_f32m8(
                        behind, __riscv_vfmul_vv_f32m8(tau, behind, vl), front, vl
                    ),
                    vl
                );
            }
        }
        asm volatile("" ::: "memory");
        return fronts != 0;
    }

}  // namespace light_k
