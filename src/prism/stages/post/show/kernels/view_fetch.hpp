// A file's view transform on the pack CPU (prism_reference.post.view, the form view.h
// describes), for both forms (the post step, SHOW's class): a tile's or band's pixels'
// cube pages from its colour planes (three pages in window order), read into slots in
// passes of 16-pixel parts, then each pixel's cube coordinates again and its value by
// tetrahedral interpolation of the 16-bit entries into three planes in the same order.
#pragma once

#include <riscv_vector.h>
#include <stdint.h>

#include "view.h"

namespace view_fetch {

    constexpr uint32_t kPart = 16;  // words a pass takes at a time
    constexpr uint32_t kPlaneWords = kViewPageBytes / 4;
    static_assert(kViewSlots >= kPart);                // a part's pages fit the slots
    static_assert(kViewWorkBytes == 4 * kPlaneWords);  // a word a pixel

    // cell / 7 (kViewCellsMost at most) by a product and a shift.
    inline vuint32m2_t brick_of(vuint32m2_t cell, size_t vl) {
        return __riscv_vsrl_vx_u32m2(
            __riscv_vmul_vx_u32m2(cell, kViewSevenths, vl), kViewSeventhsShift, vl
        );
    }

    inline vfloat32m2_t splat(uint32_t bits, size_t vl) {
        return __riscv_vreinterpret_v_u32m2_f32m2(__riscv_vmv_v_x_u32m2(bits, vl));
    }

    // log2 of positive normal values: the exponent plus the table at the mantissa's
    // top kViewLogBits bits, linear over the rest to the next entry (prism_reference
    // log2_of).
    inline vfloat32m2_t log2_of(const uint32_t* view, vfloat32m2_t x, size_t vl) {
        constexpr uint32_t kRest = 23 - kViewLogBits;
        const vuint32m2_t bits = __riscv_vreinterpret_v_f32m2_u32m2(x);
        const vfloat32m2_t exponent = __riscv_vfcvt_f_x_v_f32m2(
            __riscv_vsub_vx_i32m2(
                __riscv_vreinterpret_v_u32m2_i32m2(__riscv_vsrl_vx_u32m2(bits, 23, vl)),
                127,
                vl
            ),
            vl
        );
        const vuint32m2_t mantissa = __riscv_vand_vx_u32m2(bits, 0x7FFFFF, vl);
        const vuint32m2_t at = __riscv_vsll_vx_u32m2(
            __riscv_vsrl_vx_u32m2(mantissa, kRest, vl), 2, vl
        );
        const vfloat32m2_t fraction = __riscv_vfmul_vv_f32m2(
            __riscv_vfcvt_f_xu_v_f32m2(
                __riscv_vand_vx_u32m2(mantissa, (1u << kRest) - 1, vl), vl
            ),
            splat(0x39000000u, vl),  // 2^-13
            vl
        );
        const float* table = reinterpret_cast<const float*>(view + kViewLogAt);
        const vfloat32m2_t low = __riscv_vluxei32_v_f32m2(table, at, vl);
        const vfloat32m2_t step = __riscv_vfsub_vv_f32m2(
            __riscv_vluxei32_v_f32m2(table + 1, at, vl), low, vl
        );
        return __riscv_vfadd_vv_f32m2(
            __riscv_vfadd_vv_f32m2(low, __riscv_vfmul_vv_f32m2(fraction, step, vl), vl),
            exponent,
            vl
        );
    }

    // Channel k's cube coordinate (cells) of the pixels at word `w` of the colour
    // planes `rgb`: the 3 x 3 product's row k, clamped, log2, scaled, clamped.
    inline vfloat32m2_t coordinate(
        const uint32_t* view, const float* rgb, uint32_t w, uint32_t k, size_t vl
    ) {
        const uint32_t* m = view + kViewMatrix + 3 * k;
        vfloat32m2_t y = __riscv_vfadd_vv_f32m2(
            __riscv_vfmul_vv_f32m2(
                __riscv_vle32_v_f32m2(rgb + w, vl), splat(m[0], vl), vl
            ),
            __riscv_vfmul_vv_f32m2(
                __riscv_vle32_v_f32m2(rgb + kPlaneWords + w, vl), splat(m[1], vl), vl
            ),
            vl
        );
        y = __riscv_vfadd_vv_f32m2(
            y,
            __riscv_vfmul_vv_f32m2(
                __riscv_vle32_v_f32m2(rgb + 2 * kPlaneWords + w, vl),
                splat(m[2], vl),
                vl
            ),
            vl
        );
        y = __riscv_vfmin_vv_f32m2(
            __riscv_vfmax_vv_f32m2(y, splat(view[kViewFloor], vl), vl),
            splat(view[kViewCeiling], vl),
            vl
        );
        const vfloat32m2_t c = __riscv_vfmul_vv_f32m2(
            __riscv_vfsub_vv_f32m2(log2_of(view, y, vl), splat(view[kViewLow], vl), vl),
            splat(view[kViewScale], vl),
            vl
        );
        return __riscv_vfmin_vv_f32m2(
            __riscv_vfmax_vv_f32m2(c, splat(0, vl), vl),
            __riscv_vfcvt_f_xu_v_f32m2(__riscv_vmv_v_x_u32m2(view[kViewCells], vl), vl),
            vl
        );
    }

    // A coordinate's cell (at most cells - 1).
    inline vuint32m2_t cell_of(const uint32_t* view, vfloat32m2_t c, size_t vl) {
        return __riscv_vminu_vx_u32m2(
            __riscv_vfcvt_rtz_xu_f_v_u32m2(c, vl), view[kViewCells] - 1, vl
        );
    }

    // The cube page of each pixel at word `w` into `work`.
    inline void pages_of(
        const uint32_t* view, const float* rgb, uint32_t* work, uint32_t w, size_t vl
    ) {
        const uint32_t across = view[kViewAcross];
        vuint32m2_t page = __riscv_vmv_v_x_u32m2(0, vl);
        for (uint32_t k = 0; k < 3; ++k) {
            const vuint32m2_t brick = brick_of(
                cell_of(view, coordinate(view, rgb, w, k, vl), vl), vl
            );
            const uint32_t weight = k == 0 ? 1 : (k == 1 ? across : across * across);
            page = __riscv_vmacc_vx_u32m2(page, weight, brick, vl);
        }
        __riscv_vse32_v_u32m2(work + w, page, vl);
    }

    // The parts (kPart words) of [first, end) given slots: each pixel's page found
    // among the slots held (`held` pages in `slot_pages`) or added, its word of `work`
    // then its slot's byte offset (a part's words once all its pages are held). The
    // first part that would pass kViewSlots: its word (`end` when none).
    inline uint32_t slots_of(
        uint32_t* work,
        uint32_t first,
        uint32_t end,
        uint32_t* slot_pages,
        uint32_t& held
    ) {
        for (uint32_t w = first; w < end; w += kPart) {
            uint32_t added = 0;
            uint32_t offsets[kPart];
            for (uint32_t i = 0; i < kPart; ++i) {
                const uint32_t page = work[w + i];
                uint32_t s = 0;
                while (s < held + added && slot_pages[s] != page) {
                    ++s;
                }
                if (s == held + added) {
                    if (held + added == kViewSlots) {
                        return w;  // this part starts the next pass
                    }
                    slot_pages[s] = page;
                    ++added;
                }
                offsets[i] = s * kViewPageBytes;
            }
            for (uint32_t i = 0; i < kPart; ++i) {
                work[w + i] = offsets[i];
            }
            held += added;
        }
        return end;
    }

    // `weight` times the entry at byte `corner` of the slots, each channel added to
    // `out` (three planes at word `w`; `first`: stored, not added).
    inline void add_corner(
        const uint32_t* slots,
        vuint32m2_t corner,
        vfloat32m2_t weight,
        float* out,
        uint32_t w,
        bool first,
        size_t vl
    ) {
        const vuint32m2_t rg = __riscv_vluxei32_v_u32m2(slots, corner, vl);
        const vuint32m2_t bw = __riscv_vluxei32_v_u32m2(
            slots, __riscv_vadd_vx_u32m2(corner, 4, vl), vl
        );
        for (uint32_t ch = 0; ch < 3; ++ch) {
            const vuint32m2_t entry =
                (ch == 0 ? __riscv_vand_vx_u32m2(rg, 0xFFFF, vl)
                         : (ch == 1 ? __riscv_vsrl_vx_u32m2(rg, 16, vl)
                                    : __riscv_vand_vx_u32m2(bw, 0xFFFF, vl)));
            const vfloat32m2_t term = __riscv_vfmul_vv_f32m2(
                weight, __riscv_vfcvt_f_xu_v_f32m2(entry, vl), vl
            );
            float* plane = out + ch * kPlaneWords + w;
            __riscv_vse32_v_f32m2(
                plane,
                first ? term
                      : __riscv_vfadd_vv_f32m2(
                            __riscv_vle32_v_f32m2(plane, vl), term, vl
                        ),
                vl
            );
        }
    }

    // The fraction of the axis numbered `axis` (0 r, 1 g, 2 b).
    inline vfloat32m2_t fraction_of(
        vfloat32m2_t fr, vfloat32m2_t fg, vfloat32m2_t fb, vuint32m2_t axis, size_t vl
    ) {
        const vfloat32m2_t gb = __riscv_vmerge_vvm_f32m2(
            fb, fg, __riscv_vmseq_vx_u32m2_b16(axis, 1, vl), vl
        );
        return __riscv_vmerge_vvm_f32m2(
            gb, fr, __riscv_vmseq_vx_u32m2_b16(axis, 0, vl), vl
        );
    }

    // A step of the axis numbered `axis` in a page: 8, 64, 512 bytes.
    inline vuint32m2_t step_of(vuint32m2_t axis, size_t vl) {
        return __riscv_vsll_vv_u32m2(
            __riscv_vmv_v_x_u32m2(kViewEntryBytes, vl),
            __riscv_vmul_vx_u32m2(axis, 3, vl),
            vl
        );
    }

    // Channel k's fraction over its cell and its node's bytes in the brick added to
    // `base`.
    inline vfloat32m2_t fraction_at(
        const uint32_t* view,
        const float* rgb,
        uint32_t w,
        uint32_t k,
        vuint32m2_t& base,
        size_t vl
    ) {
        const vfloat32m2_t c = coordinate(view, rgb, w, k, vl);
        const vuint32m2_t cell = cell_of(view, c, vl);
        const vuint32m2_t node = __riscv_vsub_vv_u32m2(
            cell, __riscv_vmul_vx_u32m2(brick_of(cell, vl), kViewBrickCells, vl), vl
        );
        const uint32_t step = k == 0 ? kViewEntryBytes
                                     : (k == 1 ? kViewStepG : kViewStepB);
        base = __riscv_vmacc_vx_u32m2(base, step, node, vl);
        return __riscv_vfsub_vv_f32m2(c, __riscv_vfcvt_f_xu_v_f32m2(cell, vl), vl);
    }

    // The pixels at word `w`: each one's value by tetrahedral interpolation of its
    // cell's corners in its slot (its offset in `work`), into `out` (three planes;
    // `rgb` itself allowed: a pixel's colour is read before its value is written).
    inline void values_of(
        const uint32_t* view,
        const float* rgb,
        const uint32_t* work,
        const uint32_t* slots,
        float* out,
        uint32_t w,
        size_t vl
    ) {
        vuint32m2_t base = __riscv_vle32_v_u32m2(work + w, vl);
        const vfloat32m2_t fr = fraction_at(view, rgb, w, 0, base, vl);
        const vfloat32m2_t fg = fraction_at(view, rgb, w, 1, base, vl);
        const vfloat32m2_t fb = fraction_at(view, rgb, w, 2, base, vl);
        // the axes by falling fraction, ties to the lower axis (r, g, b)
        const vbool16_t r_over_g = __riscv_vmfge_vv_f32m2_b16(fr, fg, vl);
        const vbool16_t r_over_b = __riscv_vmfge_vv_f32m2_b16(fr, fb, vl);
        const vbool16_t g_over_b = __riscv_vmfge_vv_f32m2_b16(fg, fb, vl);
        const vbool16_t r_first = __riscv_vmand_mm_b16(r_over_g, r_over_b, vl);
        const vbool16_t g_first = __riscv_vmandn_mm_b16(g_over_b, r_first, vl);
        const vbool16_t b_first = __riscv_vmnor_mm_b16(r_first, g_first, vl);
        const vuint32m2_t first = __riscv_vmerge_vxm_u32m2(
            __riscv_vmerge_vxm_u32m2(__riscv_vmv_v_x_u32m2(2, vl), 1, g_first, vl),
            0,
            r_first,
            vl
        );
        // r first: g or b; g first: r or b; b first: r or g
        vuint32m2_t second = __riscv_vmerge_vxm_u32m2(
            __riscv_vmv_v_x_u32m2(2, vl), 1, g_over_b, vl
        );
        second = __riscv_vmerge_vvm_u32m2(
            second,
            __riscv_vmerge_vxm_u32m2(__riscv_vmv_v_x_u32m2(2, vl), 0, r_over_b, vl),
            g_first,
            vl
        );
        second = __riscv_vmerge_vvm_u32m2(
            second,
            __riscv_vmerge_vxm_u32m2(__riscv_vmv_v_x_u32m2(1, vl), 0, r_over_g, vl),
            b_first,
            vl
        );
        const vuint32m2_t third = __riscv_vrsub_vx_u32m2(
            __riscv_vadd_vv_u32m2(first, second, vl), 3, vl
        );
        const vfloat32m2_t fa = fraction_of(fr, fg, fb, first, vl);
        const vfloat32m2_t fbb = fraction_of(fr, fg, fb, second, vl);
        const vfloat32m2_t fc = fraction_of(fr, fg, fb, third, vl);
        const vuint32m2_t corner_a = __riscv_vadd_vv_u32m2(
            base, step_of(first, vl), vl
        );
        add_corner(
            slots,
            base,
            __riscv_vfsub_vv_f32m2(splat(0x3F800000u, vl), fa, vl),
            out,
            w,
            true,
            vl
        );
        add_corner(
            slots, corner_a, __riscv_vfsub_vv_f32m2(fa, fbb, vl), out, w, false, vl
        );
        add_corner(
            slots,
            __riscv_vadd_vv_u32m2(corner_a, step_of(second, vl), vl),
            __riscv_vfsub_vv_f32m2(fbb, fc, vl),
            out,
            w,
            false,
            vl
        );
        add_corner(
            slots,
            __riscv_vadd_vx_u32m2(base, kViewEntryBytes + kViewStepG + kViewStepB, vl),
            fc,
            out,
            w,
            false,
            vl
        );
        const vfloat32m2_t unit = splat(0x37800080u, vl);  // float32(1 / 65535)
        for (uint32_t ch = 0; ch < 3; ++ch) {
            float* plane = out + ch * kPlaneWords + w;
            __riscv_vse32_v_f32m2(
                plane,
                __riscv_vfmul_vv_f32m2(__riscv_vle32_v_f32m2(plane, vl), unit, vl),
                vl
            );
        }
    }

    // A view's counts: tiles (or bands) converted, passes, pages asked.
    struct ViewCounts {
        uint32_t items = 0, passes = 0, pages = 0;
    };

    // The words [first_word, end_word) of the colour planes at `rgb` through the view
    // into the planes at `out` (`rgb` itself allowed): each pixel's page into `work`,
    // then passes: the pass's distinct cube pages (at most kViewSlots) read into
    // `slots` by ask(pages, count) (false: gave up), its pixels interpolated. False:
    // gave up.
    template <typename Ask>
    bool view_planes(
        const uint32_t* view,
        const float* rgb,
        float* out,
        uint32_t first_word,
        uint32_t end_word,
        uint32_t* work,
        uint32_t slots,
        Ask&& ask,
        ViewCounts& counts
    ) {
        for (uint32_t w = first_word; w < end_word;) {
            const size_t vl = __riscv_vsetvl_e32m2(end_word - w);
            pages_of(view, rgb, work, w, vl);
            w += vl;
        }
        uint32_t slot_pages[kViewSlots];
        for (uint32_t w = first_word; w < end_word;) {
            uint32_t held = 0;
            const uint32_t next = slots_of(work, w, end_word, slot_pages, held);
            if (!ask(slot_pages, held)) {
                return false;
            }
            counts.passes++;
            counts.pages += held;
            while (w < next) {
                const size_t vl = __riscv_vsetvl_e32m2(next - w);
                values_of(
                    view,
                    rgb,
                    work,
                    reinterpret_cast<const uint32_t*>(slots),
                    out,
                    w,
                    vl
                );
                w += vl;
            }
        }
        counts.items++;
        asm volatile("fence" ::: "memory");
        return true;
    }

}  // namespace view_fetch
