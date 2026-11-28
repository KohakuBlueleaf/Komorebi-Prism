// T on the pack CPU, both forms' (the material step's glass layer of a DEPTH view,
// SHADE's transmit mode): the product of tau (1 - F0)^2 of every glass record covering
// a pixel (FILL's edge rule, its 1/z held as FILL holds it) nearer than the opaque
// layer's 1/z, three float pages in the window's order; then its kept codes
// (core/include/thread/transmit.h).
#pragma once

#include <stdint.h>

#include <riscv_vector.h>

#include "../../../../core/include/thread/transmit.h"
#include "../../../raster/kernels/common/layouts.hpp"
#include "shade.h"

namespace transmit_k {

    // (1 - F0)^2 as float32 bits, F0 = 0.04: a pane's two faces at normal incidence
    // (prism_reference.direct.transmit LOSS; direct.light's host checks the two).
    constexpr uint32_t kTransmitLossBits = 0x3F6BEDFA;
    constexpr uint32_t kTransmitPlanes = 3;  // T's red, green, blue: pages 1 to 3

    // A float of `bits`, made in a register (no constant in local memory).
    inline float bits_float(uint32_t bits) {
        asm volatile("" : "+r"(bits));
        float value;
        __builtin_memcpy(&value, &bits, 4);
        return value;
    }

    // A box column word as a float: float32 bits in a wide build (grid.h), else its
    // low half's IEEE float16 (a whole number of pixels, at least 0).
    inline float box_column(uint32_t word) {
#ifdef RASTER_WIDE
        return bits_float(word);
#else
        const uint32_t half = word & 0xFFFF;
        if ((half & 0x7FFF) == 0) {
            return 0.0f;
        }
        const uint32_t exponent = half >> 10 & 0x1F, mantissa = half & 0x3FF;
        return bits_float((exponent + 112) << 23 | mantissa << 13);
#endif
    }

    // A row's 16 lanes of a half h of a plane's row pair in the window's order: lane
    // i is word 32 h + 2 i + (the row's parity), column 8 (w / 16) + (w / 2) mod 8
    // (post/show/kernels/convert.hpp window_word). Their words: each lane's pixel
    // centre's x, 16 a half.
    constexpr uint32_t kLanePx = 0, kLaneWords = 32, kLaneSide = 16;

    inline void lane_words(uint32_t* words, uint32_t tile_x) {
        const size_t vl = __riscv_vsetvl_e32m4(kLaneSide);
        const vuint32m4_t i = __riscv_vid_v_u32m4(vl);
        for (uint32_t h = 0; h < 2; ++h) {
            const vuint32m4_t w = __riscv_vadd_vx_u32m4(
                __riscv_vsll_vx_u32m4(i, 1, vl), 32 * h, vl
            );
            const vuint32m4_t column = __riscv_vadd_vv_u32m4(
                __riscv_vsll_vx_u32m4(__riscv_vsrl_vx_u32m4(w, 4, vl), 3, vl),
                __riscv_vand_vx_u32m4(__riscv_vsrl_vx_u32m4(w, 1, vl), 7, vl),
                vl
            );
            __riscv_vse32_v_f32m4(
                reinterpret_cast<float*>(words + kLanePx + kLaneSide * h),
                __riscv_vfadd_vf_f32m4(
                    __riscv_vfcvt_f_xu_v_f32m4(
                        __riscv_vadd_vx_u32m4(column, 32 * tile_x, vl), vl
                    ),
                    0.5f,
                    vl
                ),
                vl
            );
        }
        asm volatile("" ::: "memory");
    }

    // (a px + b py) + c as FILL's plane: each product rounded, then each sum.
    inline vfloat32m4_t plane_at(
        vfloat32m4_t px, float a, float bpy, float c, size_t vl
    ) {
        return __riscv_vfadd_vf_f32m4(
            __riscv_vfadd_vf_f32m4(__riscv_vfmul_vf_f32m4(px, a, vl), bpy, vl), c, vl
        );
    }

    // A glass record's numbers: its edges, 1/z plane and range, box, factors.
    struct Pane {
        float a[3], b[3], c[3], t[3], w[3], least, most, x0, x1;
        int32_t first, last;  // its rows in the tile
        float factor[kTransmitPlanes];
    };

    // The record's pane in the tile row `tile_y`, its rows clipped to [first_row,
    // end_row); false when its material is none of `materials` (each kMaterialWords
    // words at `material_words`).
    inline bool pane_of(
        const volatile uint32_t* record,
        const uint32_t* material_words,
        uint32_t materials,
        uint32_t tile_y,
        int32_t first_row,
        int32_t end_row,
        float loss,
        Pane& pane
    ) {
        const uint32_t material = record[kRecShade] & 0xFFFF;
        if (material >= materials) {
            return false;
        }
        const uint32_t* tau = material_words + kMaterialWords * material + kMaterialTau;
        for (uint32_t k = 0; k < 3; ++k) {
            pane.a[k] = bits_float(record[fill_k::kRecA + k]);
            pane.b[k] = bits_float(record[fill_k::kRecB + k]);
            pane.c[k] = bits_float(record[fill_k::kRecC + k]);
            pane.t[k] = bits_float(record[fill_k::kRecT + k]);
            pane.w[k] = bits_float(record[fill_k::kRecW + k]);
            pane.factor[k] = bits_float(tau[k]) * loss;
        }
        pane.least = bits_float(record[fill_k::kRecWLeast]);
        pane.most = bits_float(record[fill_k::kRecWMost]);
        pane.x0 = box_column(record[fill_k::kRecX0]);
        pane.x1 = box_column(record[fill_k::kRecX1]);
        const int32_t top = 32 * static_cast<int32_t>(tile_y);
        pane.first = static_cast<int32_t>(record[fill_k::kRecY0]) - top;
        pane.last = static_cast<int32_t>(record[fill_k::kRecY1]) - top;
        pane.first = pane.first < first_row ? first_row : pane.first;
        pane.last = pane.last > end_row - 1 ? end_row - 1 : pane.last;
        return true;
    }

    // T 1 over the band's rows of the three pages at `t`.
    inline void t_ones(float* const* t, int32_t first_row, int32_t end_row, size_t vl) {
        const vfloat32m8_t one = __riscv_vfmv_v_f_f32m8(1.0f, vl);
        for (uint32_t c = 0; c < kTransmitPlanes; ++c) {
            for (int32_t pair = first_row / 2; pair < end_row / 2; ++pair) {
                __riscv_vse32_v_f32m8(t[c] + 64 * pair, one, vl);
                __riscv_vse32_v_f32m8(t[c] + 64 * pair + 32, one, vl);
            }
        }
    }

    // The pane's rows of the band times its factors where it covers a pixel nearer
    // than `depth` (the opaque layer's 1/z page), the T pages at `t`; a row's half
    // its 16 words at a stride of 2.
    inline void pane_rows(
        const Pane& pane,
        const uint32_t* lanes,
        uint32_t tile_y,
        const float* depth,
        float* const* t
    ) {
        const size_t vl = __riscv_vsetvl_e32m4(kLaneSide);
        constexpr ptrdiff_t kStride = 8;  // bytes: every other word of a half
        for (int32_t row = pane.first; row <= pane.last; ++row) {
            const float py = static_cast<float>(32 * tile_y + row) + 0.5f;
            for (uint32_t h = 0; h < 2; ++h) {
                const vfloat32m4_t px = __riscv_vle32_v_f32m4(
                    reinterpret_cast<const float*>(lanes + kLanePx + kLaneSide * h), vl
                );
                vbool8_t in = __riscv_vmand_mm_b8(
                    __riscv_vmfgt_vf_f32m4_b8(px, pane.x0, vl),
                    __riscv_vmflt_vf_f32m4_b8(px, pane.x1, vl),
                    vl
                );
                for (uint32_t k = 0; k < 3; ++k) {
                    in = __riscv_vmand_mm_b8(
                        in,
                        __riscv_vmfgt_vf_f32m4_b8(
                            plane_at(px, pane.a[k], pane.b[k] * py, pane.c[k], vl),
                            pane.t[k],
                            vl
                        ),
                        vl
                    );
                }
                const vfloat32m4_t w = __riscv_vfmin_vf_f32m4(
                    __riscv_vfmax_vf_f32m4(
                        plane_at(px, pane.w[0], pane.w[1] * py, pane.w[2], vl),
                        pane.least,
                        vl
                    ),
                    pane.most,
                    vl
                );
                const uint32_t at = 64 * static_cast<uint32_t>(row / 2) + 32 * h +
                    static_cast<uint32_t>(row % 2);
                in = __riscv_vmand_mm_b8(
                    in,
                    __riscv_vmfgt_vv_f32m4_b8(
                        w, __riscv_vlse32_v_f32m4(depth + at, kStride, vl), vl
                    ),
                    vl
                );
                for (uint32_t c = 0; c < kTransmitPlanes; ++c) {
                    const vfloat32m4_t value = __riscv_vlse32_v_f32m4(
                        t[c] + at, kStride, vl
                    );
                    __riscv_vsse32_v_f32m4(
                        t[c] + at,
                        kStride,
                        __riscv_vfmul_vf_f32m4_mu(in, value, value, pane.factor[c], vl),
                        vl
                    );
                }
            }
        }
    }

    // The codes of the band's rows [first_row, end_row) of T (three pages from `t`,
    // red, green, blue; 0: every texel 1) into `payload`, a kept texel the mean of a 2
    // x 2 of pixels (transmit.h); `channels` 1 (a byte, red's) or 3 (a word). Its
    // bytes.
    inline uint32_t t_codes(
        uint32_t t,
        uint32_t first_row,
        uint32_t end_row,
        uint32_t channels,
        uint32_t payload
    ) {
        const size_t vl = __riscv_vsetvl_e32m4(TRANSMIT_SIDE);
        const uint32_t row_bytes = TRANSMIT_SIDE * (channels == 1 ? 1u : 4u);
        for (uint32_t pair = first_row / 2u; pair < end_row / 2u; ++pair) {
            vuint32m4_t word = __riscv_vmv_v_x_u32m4(0, vl);
            for (uint32_t c = 0; c < channels; ++c) {
                vuint32m4_t code = __riscv_vmv_v_x_u32m4(TRANSMIT_ONE, vl);
                if (t != 0) {
                    // the window's words 64 p + 4 x + q: rows 2 p + q % 2, column 2 x
                    // + q / 2 (post/show/kernels/convert.hpp window_word)
                    const float* at = reinterpret_cast<const float*>(
                                          t + c * fill_k::kOutPageBytes
                                      ) +
                        64u * pair;
                    const vfloat32m4_t mean = __riscv_vfmul_vf_f32m4(
                        __riscv_vfadd_vv_f32m4(
                            __riscv_vfadd_vv_f32m4(
                                __riscv_vlse32_v_f32m4(at, 16, vl),
                                __riscv_vlse32_v_f32m4(at + 1, 16, vl),
                                vl
                            ),
                            __riscv_vfadd_vv_f32m4(
                                __riscv_vlse32_v_f32m4(at + 2, 16, vl),
                                __riscv_vlse32_v_f32m4(at + 3, 16, vl),
                                vl
                            ),
                            vl
                        ),
                        bits_float(0x3E800000),  // 1/4
                        vl
                    );
                    code = __riscv_vminu_vx_u32m4(
                        __riscv_vfcvt_rtz_xu_f_v_u32m4(
                            __riscv_vfmax_vf_f32m4(
                                __riscv_vfadd_vf_f32m4(
                                    __riscv_vfmul_vf_f32m4(
                                        mean, bits_float(0x437F0000), vl
                                    ),
                                    0.5f,
                                    vl
                                ),
                                0.0f,
                                vl
                            ),
                            vl
                        ),
                        TRANSMIT_ONE,
                        vl
                    );
                }
                word = __riscv_vor_vv_u32m4(
                    word, __riscv_vsll_vx_u32m4(code, 8u * c, vl), vl
                );
            }
            const uint32_t to = payload + (pair - first_row / 2u) * row_bytes;
            if (channels == 1) {
                __riscv_vse8_v_u8m1(
                    reinterpret_cast<uint8_t*>(to),
                    __riscv_vncvt_x_x_w_u8m1(__riscv_vncvt_x_x_w_u16m2(word, vl), vl),
                    vl
                );
            } else {
                __riscv_vse32_v_u32m4(reinterpret_cast<uint32_t*>(to), word, vl);
            }
        }
        asm volatile("fence" ::: "memory");
        return (end_row - first_row) / 2u * row_bytes;
    }

}  // namespace transmit_k
