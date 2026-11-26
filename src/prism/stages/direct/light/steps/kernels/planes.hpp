// The light step on the pack CPU: a quarter tile's planes from the tile's planes in L1
// into Dst (the forms' item pages of pack/dst.hpp kLightSource), the glass's in front,
// weighted albedo and tau C; the item ring's copy_in and glass_in, adapted.
#pragma once

#include <stdint.h>

#include "../../kernels/pack/quarter.hpp"

namespace light_step {

    using namespace light_k;

    // The planes a form reads: its surface's ten pages, the first layer's visibility
    // pages (the merged 1/z, the colour, the material word) and the glass form's glass
    // layer's (its 1/z and material word).
    struct FormPlanes {
        uint32_t surface;
        uint32_t opaque;
        uint32_t glass_layer;
        bool glass;

        // The L1 page of the form's item page `at` (mover_a/items.hpp page_source).
        uint32_t page(uint32_t at) const {
            constexpr uint32_t kSurfacePages = 2 * fill_k::kPlanes;
            if (at < kSurfacePages) {
                return surface + at * kOutPageBytes;
            }
            if (at >= kLightGlassC) {  // C, then the merged 1/z
                return opaque +
                    (at < kLightGlassDepth ? 1 + at - kLightGlassC : 0) * kOutPageBytes;
            }
            // the frame's (glass: the glass layer's) 1/z, its material word
            return (glass ? glass_layer : opaque) +
                (at == kSurfacePages ? 0 : fill_k::kPlanes - 1) * kOutPageBytes;
        }
    };

    // The quarter's planes into Dst.
    inline void planes_in(const FormPlanes& from, uint32_t quarter, size_t vl) {
        for (uint32_t plane = 0; plane < kLvPlanes; ++plane) {
            const uint32_t* source =
                (reinterpret_cast<const uint32_t*>(from.page(kLightSource[plane])) +
                 kQuarterWords * quarter);
            for (uint32_t i = 0; i < kQuarterWords; i += 32) {
                __riscv_vse32_v_u32m8(
                    const_cast<uint32_t*>(window() + kQuarterWords * plane + i),
                    __riscv_vle32_v_u32m8(source + i, vl),
                    vl
                );
            }
        }
        asm volatile("" ::: "memory");
    }

    // Glass, the quarter's rows: in front (bit 31 clear, 1/z above the merged; a tie
    // behind) the glass word, else bit 31; (1 - max tau) a; tau C. True if any.
    __attribute__((noinline)) bool glass_planes_in(
        const FormPlanes& from,
        uint32_t quarter,
        const uint32_t* material_words,
        size_t vl
    ) {
        auto page_of = [&](uint32_t at) -> const uint32_t* {
            return reinterpret_cast<const uint32_t*>(from.page(at)) +
                kQuarterWords * quarter;
        };
        const uint32_t* glass_material = page_of(kLightItemPlanes - 1);
        const uint32_t* glass_depth = page_of(kLightItemPlanes - 2);
        const uint32_t* depth = page_of(kLightGlassDepth);
        uint32_t fronts = 0;
        for (uint32_t i = 0; i < kQuarterWords; i += 32) {
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
                const_cast<uint32_t*>(window() + kQuarterWords * kLvMaterial + i),
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
                        window() + kQuarterWords * (kLvAlbedo + channel) + i
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
                        window() + 64 * (kLvC / 2) + kQuarterWords * channel + i
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

}  // namespace light_step
