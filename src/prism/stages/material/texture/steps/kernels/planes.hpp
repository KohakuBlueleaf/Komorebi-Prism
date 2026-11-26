// The material step's planes on the pack CPU, all in L1: a layer's rows into Dst (the
// opaque layer's as near or nearer: triangle -1 when merging), rows copied between
// pages, and rows taken from another layer's pages where the depth row in Dst is set.
#pragma once

#include <stdint.h>

#include "../../kernels/pack/vector.hpp"

namespace material_step {

    using namespace shade_k;

    // Rows [first_row, end_row) of the planes at `plane_words` into Dst (two rows: 64
    // words); merging, triangle -1 unless nearer than `opaque_words`' (1/z as unsigned
    // bits, a tie to it). pack/copy_in.hpp's copy_in on pages in L1.
    [[gnu::noinline]] inline void planes_in(
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

    // Words [first_word, first_word + words) of page `from_page` at `from` to page
    // `to_page` at `to`.
    inline void copy_page_rows(
        uint32_t to,
        uint32_t to_page,
        uint32_t from,
        uint32_t from_page,
        uint32_t first_word,
        uint32_t words,
        size_t vl
    ) {
        uint32_t* target = reinterpret_cast<uint32_t*>(to) + to_page * kPlaneWords;
        const uint32_t* source = reinterpret_cast<const uint32_t*>(from) +
            from_page * kPlaneWords;
        for (uint32_t at = first_word; at < first_word + words; at += 32) {
            __riscv_vse32_v_u32m8(
                target + at, __riscv_vle32_v_u32m8(source + at, vl), vl
            );
        }
        asm volatile("" ::: "memory");
    }

    // Words [first_word, + words) of page `page` at `to` from the same page at `from`
    // where Dst's depth row is not 0 (the merging layer's pixel taken).
    inline void take_page_rows(
        uint32_t to,
        uint32_t from,
        uint32_t page,
        uint32_t first_word,
        uint32_t words,
        size_t vl
    ) {
        uint32_t* target = reinterpret_cast<uint32_t*>(to) + page * kPlaneWords;
        const uint32_t* source = reinterpret_cast<const uint32_t*>(from) +
            page * kPlaneWords;
        for (uint32_t at = first_word; at < first_word + words; at += 32) {
            const vbool4_t take = __riscv_vmsne_vx_u32m8_b4(
                __riscv_vle32_v_u32m8(const_cast<const uint32_t*>(window() + at), vl),
                0,
                vl
            );
            __riscv_vse32_v_u32m8(
                target + at,
                __riscv_vmerge_vvm_u32m8(
                    __riscv_vle32_v_u32m8(target + at, vl),
                    __riscv_vle32_v_u32m8(source + at, vl),
                    take,
                    vl
                ),
                vl
            );
        }
        asm volatile("" ::: "memory");
    }

    // Stores to L1 finished: a fence, then a load of the word at `address` used.
    inline void landed(uint32_t address) {
        asm volatile("fence" ::: "memory");
        const uint32_t last_word = *reinterpret_cast<volatile uint32_t*>(address);
        asm volatile("and x0, x0, %0" : : "r"(last_word) : "memory");
    }

}  // namespace material_step
