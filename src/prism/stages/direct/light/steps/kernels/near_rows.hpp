// The light step on the pack CPU with the one-tile product: a row's I at kSxIndirect
// from the plane near.light, E at the tile's half pixels joined to the full pixels by
// the upsample's four taps a pixel and their weights (both in the plane), then the
// row's colour.
#pragma once

#include <stdint.h>

#include <riscv_vector.h>

#include "../../../../indirect/near_tile/steps/kernels/near_tile_step.h"
#include "../../kernels/pack/passes.hpp"

namespace light_step {

    using near_tile_step::kHalfTile;
    using near_tile_step::kNearCols;
    using near_tile_step::kNearRows;
    using near_tile_step::kNearTaps;
    using near_tile_step::kNearWeightsAt;

    // The plane near.light as the upsample reads it: E (a channel's 256 half pixels
    // after another), the taps' weights (a tap's 1,024 pixels after another), the
    // tile's last half row and half column inside the frame.
    struct NearPlanes {
        const float* e;
        const float* weights;
        uint32_t last_row, last_col;
    };

    inline NearPlanes near_planes(uint32_t plane) {
        const uint32_t* words = reinterpret_cast<const uint32_t*>(plane);
        return {
            reinterpret_cast<const float*>(words),
            reinterpret_cast<const float*>(words + kNearWeightsAt),
            words[kNearRows] - 1,
            words[kNearCols] - 1
        };
    }

    // Row r's I, channel `channel`, into Dst vector `vector`, its 32 lanes in two
    // halves of 16 (each 4 vector registers): the sum over the taps (dy, dx) of
    // weight x E at half row min(r / 2 + dy, last row), half column min(x / 2 + dx,
    // last column).
    inline void near_channel(
        const NearPlanes& p, uint32_t r, uint32_t channel, uint32_t vector
    ) {
        constexpr size_t kHalf = kHalfTile;
        for (uint32_t h = 0; h < 2; ++h) {
            vfloat32m4_t sum = __riscv_vfmv_v_f_f32m4(0.0f, kHalf);
            for (uint32_t tap = 0; tap < kNearTaps; ++tap) {
                const uint32_t dy = tap >> 1, dx = tap & 1;
                const uint32_t y = (r >> 1) + dy, yy = y < p.last_row ? y : p.last_row;
                const vuint32m4_t xx = __riscv_vminu_vx_u32m4(
                    __riscv_vadd_vx_u32m4(
                        __riscv_vsrl_vx_u32m4(__riscv_vid_v_u32m4(kHalf), 1, kHalf),
                        8 * h + dx,
                        kHalf
                    ),
                    p.last_col,
                    kHalf
                );
                const vfloat32m4_t e = __riscv_vrgather_vv_f32m4(
                    __riscv_vle32_v_f32m4(
                        p.e + kHalfTile * kHalfTile * channel + kHalfTile * yy, kHalf
                    ),
                    xx,
                    kHalf
                );
                sum = __riscv_vfmacc_vv_f32m4(
                    sum,
                    __riscv_vle32_v_f32m4(
                        p.weights + 1024 * tap + 32 * r + kHalf * h, kHalf
                    ),
                    e,
                    kHalf
                );
            }
            __riscv_vsse32_v_u32m4(
                const_cast<uint32_t*>(window() + word(vector) + 2 * kHalf * h),
                8,
                __riscv_vreinterpret_v_f32m4_u32m4(sum),
                kHalf
            );
        }
    }

    // Rows [first, end) of the quarter: I by near_channel, then each row's colour.
    struct NearRows {
        Pass& pass;
        const NearPlanes& planes;

        __attribute__((noinline)) bool operator()(uint32_t first, uint32_t end) {
            uint32_t* values = pass.values;
            for (uint32_t r = first; r < end; ++r) {
                const uint32_t k = r - pass.row0;
                tensix_sync();  // the vector unit is done with the row scratch
                const uint32_t at = km::wall();
                for (uint32_t channel = 0; channel < 3; ++channel) {
                    near_channel(planes, r, channel, sx_vector(kSxIndirect + channel));
                }
                asm volatile("" ::: "memory");
                setup_k::setup_pass::order(word(sx_vector(kSxIndirect + 2)) + 62);
                values[kLightProfFieldBlend] += km::wall() - at;
                light_row(k, pass.numbers, values);
                values[kLightProfRows]++;
            }
            return true;
        }
    };

}  // namespace light_step
