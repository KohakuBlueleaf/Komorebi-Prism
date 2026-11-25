// Lit SHADE merging on the pack thread: the masked layer's item merged into the opaque
// layer's frame and surface, the opaque layer's planes kept where the masked loses.
#pragma once

#include <stdint.h>

#include "surface.hpp"

namespace shade_k {

    // Rows [first_word, + words) of `planes` pages at `out` from `opaque` where the
    // depth row is 0 (the masked layer's pixel not taken).
    inline void merge_planes(
        uint32_t out,
        const uint32_t* opaque,
        uint32_t planes,
        uint32_t first_word,
        uint32_t words,
        size_t vl
    ) {
        uint32_t* to = reinterpret_cast<uint32_t*>(out);
        for (uint32_t at = first_word; at < first_word + words; at += 32) {
            const vbool4_t take = __riscv_vmsne_vx_u32m8_b4(
                __riscv_vle32_v_u32m8(const_cast<const uint32_t*>(window() + at), vl),
                0,
                vl
            );
            for (uint32_t plane = 0; plane < planes; ++plane) {
                uint32_t* value = to + plane * kPlaneWords + at;
                __riscv_vse32_v_u32m8(
                    value,
                    __riscv_vmerge_vvm_u32m8(
                        __riscv_vle32_v_u32m8(opaque + plane * kPlaneWords + at, vl),
                        __riscv_vle32_v_u32m8(value, vl),
                        take,
                        vl
                    ),
                    vl
                );
            }
        }
        asm volatile("" ::: "memory");
    }

    // The merged item: 1/z the masked layer's where taken, the material word the
    // opaque's where not; then the opaque surface's two parts from the planes ring,
    // each merged in its own five pages. False: a wait gave up.
    inline bool lit_merge(
        const compute_mail::Waits& waits,
        const Parts& parts,
        const uint32_t* plane_words,
        const uint32_t* opaque_words,
        uint32_t first_word,
        uint32_t words,
        size_t vl
    ) {
        uint32_t* depth = reinterpret_cast<uint32_t*>(parts.page(0, 0));
        for (uint32_t at = first_word; at < first_word + words; at += 32) {
            __riscv_vse32_v_u32m8(
                depth + at, __riscv_vle32_v_u32m8(plane_words + at, vl), vl
            );
        }
        asm volatile("" ::: "memory");
        merge_planes(parts.page(0, 0), opaque_words, kPlanes, first_word, words, vl);
        if (!compute_mail::pop(waits, kFieldInPlanes, 2 * kPlanes)) {
            return false;
        }
        for (uint32_t part = 1; part < kLitParts; ++part) {
            const uint32_t surface = compute_mail::front(
                waits, kFieldInPlanes, kPlanes
            );
            if (surface == 0) {
                return false;
            }
            merge_planes(
                parts.page(part, 0),
                reinterpret_cast<const uint32_t*>(surface),
                kPlanes,
                first_word,
                words,
                vl
            );
            if (!compute_mail::pop(waits, kFieldInPlanes, kPlanes)) {
                return false;
            }
        }
        return true;
    }

}  // namespace shade_k
