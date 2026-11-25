// LIGHT on the pack CPU: a float's bits and back, rsqrt on the vector unit (three
// Newton steps).
#pragma once

#include <stdint.h>

#include "../../../../../core/include/sfpu.hpp"

namespace light_k {

    using namespace pack_sfpu;

    constexpr uint32_t kMagicRsqrt = 0x5F3759DF;
    constexpr uint32_t kThreeHalvesB = 0x3FC0,
                       kHalfB = 0x3F00;  // float32's upper halves

    inline float as_float(uint32_t pattern) {
        float number;
        __builtin_memcpy(&number, &pattern, 4);
        return number;
    }

    inline uint32_t as_bits(float number) {
        uint32_t pattern;
        __builtin_memcpy(&pattern, &number, 4);
        return pattern;
    }

    // y = 1 / sqrt(x), x > 0 (kept): magic - (bits >> 1), three Newton steps; three
    // LRegs of work.
    inline void rsqrt_vector(
        uint32_t x, uint32_t y, uint32_t work0, uint32_t work1, uint32_t work2
    ) {
        TTI_SFPNOP;
        TT_SFPMOV(0, x, y, 0);
        TT_SFPSHFT(0xFFF, 0, y, kShiftImmediate);
        immediate(work0, kMagicRsqrt);
        TT_SFPIADD(0, work0, y, 2 | 4);  // y = magic - y, no condition
        TT_SFPLOADI(work0, kFloatB, kHalfB);
        mul(x, work0, work1);
        TT_SFPLOADI(work0, kFloatB, kThreeHalvesB);
        for (uint32_t step = 0; step < 3; ++step) {
            mul(work1, y, work2);
            mul(work2, y, work2);
            TT_SFPMAD(work2, ONE, work0, work2, kNegA);
            mul(y, work2, y);
        }
    }

}  // namespace light_k
