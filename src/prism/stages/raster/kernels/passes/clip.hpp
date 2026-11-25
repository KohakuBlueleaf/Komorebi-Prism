// The pack thread's scalar part of COUNT and SETUP: float32 one operation at a time,
// the near clip, a record's box and its words left raw by the vector unit.
#pragma once

#include <stdint.h>

#include "../common/layouts.hpp"

namespace setup_k {

    // float32 operations one at a time, so that nothing is fused. The cores' floats
    // round to nearest and flush results below the normal range; they cannot divide.
    inline float fsub(float a, float b) {
        volatile float result = a - b;
        return result;
    }

    inline float fmul(float a, float b) {
        volatile float result = a * b;
        return result;
    }

    inline float fadd(float a, float b) {
        volatile float result = a + b;
        return result;
    }

    inline uint32_t bits(float number) {
        uint32_t pattern;
        __builtin_memcpy(&pattern, &number, 4);
        return pattern;
    }

    inline float value(uint32_t pattern) {
        float number;
        __builtin_memcpy(&number, &pattern, 4);
        return number;
    }

    // a / b rounded to nearest even, in integers: a normal or 0, b normal, a result
    // below the normal range flushed to a signed 0 as the cores' floats do.
    inline float fdiv(float a, float b) {
        const uint32_t bits_a = bits(a), bits_b = bits(b);
        const uint32_t sign = (bits_a ^ bits_b) & 0x80000000;
        if ((bits_a & 0x7FFFFFFF) == 0) {
            return value(sign);
        }
        uint32_t significand_a = (bits_a & 0x7FFFFF) | 0x800000;
        const uint32_t significand_b = (bits_b & 0x7FFFFF) | 0x800000;
        int32_t exponent =
            (static_cast<int32_t>(bits_a >> 23 & 0xFF) -
             static_cast<int32_t>(bits_b >> 23 & 0xFF) + 127);
        if (significand_a < significand_b) {
            significand_a <<= 1;
            exponent -= 1;
        }
        // 25 quotient bits (24 and a guard bit), the remainder as the sticky bit
        uint32_t quotient = 0, remainder = significand_a;
        for (uint32_t i = 0; i < 25; ++i) {
            quotient <<= 1;
            if (remainder >= significand_b) {
                remainder -= significand_b;
                quotient |= 1;
            }
            remainder <<= 1;
        }
        uint32_t significand = quotient >> 1;
        if ((quotient & 1) && (remainder != 0 || (significand & 1))) {
            ++significand;
        }
        if (significand == 0x1000000) {
            significand >>= 1;
            ++exponent;
        }
        if (exponent <= 0) {
            return value(sign);
        }
        return (value(
            sign | static_cast<uint32_t>(exponent) << 23 | (significand & 0x7FFFFF)
        ));
    }

    // An integer below 2^24 as float32 bits (exact).
    inline uint32_t float_bits(uint32_t integer) {
        if (integer == 0) {
            return 0;
        }
        const uint32_t exponent = 31 - __builtin_clz(integer);
        return (127 + exponent) << 23 | ((integer << (23 - exponent)) & 0x7FFFFF);
    }

    // A corner: camera-space x, y, z, then red, green, blue.
    struct Corner {
        float values[6];
    };

    // The polygon of a triangle cut at z = near (prism_reference.raster.setup
    // clip_polygon): each corner beyond, and a point where an edge crosses, from its
    // corner beyond.
    uint32_t clip(const Corner* corners, float near, Corner* polygon) {
        uint32_t count = 0;
        for (uint32_t corner = 0; corner < 3; ++corner) {
            const Corner& start = corners[corner];
            const Corner& end = corners[(corner + 1) % 3];
            // z > near on the bits (near > 0, z not NaN): no float compare, whose flag
            // save and restore (frflags, fsflags) the cores' documentation leaves out.
            const int32_t near_bits = static_cast<int32_t>(bits(near));
            const bool start_beyond =
                (static_cast<int32_t>(bits(start.values[2])) > near_bits);
            const bool
                end_beyond = (static_cast<int32_t>(bits(end.values[2])) > near_bits);
            if (start_beyond) {
                polygon[count++] = start;
            }
            if (start_beyond != end_beyond) {
                const Corner& inside = start_beyond ? start : end;
                const Corner& outside = start_beyond ? end : start;
                const float fraction = (fdiv(
                    fsub(near, inside.values[2]),
                    fsub(outside.values[2], inside.values[2])
                ));
                for (uint32_t i = 0; i < 6; ++i) {
                    polygon[count].values[i] = (fadd(
                        inside.values[i],
                        fmul(fraction, fsub(outside.values[i], inside.values[i]))
                    ));
                }
                polygon[count].values[2] = near;
                ++count;
            }
        }
        return count;
    }

    // An integer in [0, 2048) as float16 bits.
    inline uint32_t half(uint32_t integer) {
        if (integer == 0) {
            return 0;
        }
        const uint32_t exponent = 31 - __builtin_clz(integer);
        return (exponent + 15) << 10 | ((integer << (10 - exponent)) & 0x3FF);
    }

    // The box of a raw record: columns x0, x1 and rows y0, y1.
    struct Box {
        int32_t first_column, last_column, first_row, last_row;
    };

    inline Box box_of(const uint32_t* words) {
        return {
            static_cast<int32_t>(words[kRawX0] - kMagic),
            static_cast<int32_t>(words[kRawX1] - kMagic),
            static_cast<int32_t>(words[kRawY0] - kMagic),
            static_cast<int32_t>(words[kRawY1] - kMagic)
        };
    }

    // Kept by the reference's cull: a non-zero area and a box that is not empty.
    inline bool kept(const uint32_t* words, const Box& box) {
        return (
            (words[kRawArea] & 0x7FFFFFFF) != 0 &&
            box.first_column <= box.last_column && box.first_row <= box.last_row
        );
    }

    // The words the vector unit leaves raw: thresholds (top-left), box, triangle.
    void finish(uint32_t* words, const Box& box, uint32_t triangle) {
        for (uint32_t corner = 0; corner < 3; ++corner) {
            const int32_t edge_a = static_cast<int32_t>(words[corner]);
            const int32_t edge_b = static_cast<int32_t>(words[3 + corner]);
            const bool top_left =
                (edge_a > 0 || ((words[corner] & 0x7FFFFFFF) == 0 && edge_b > 0));
            words[9 + corner] = top_left ? 0x80000001 : 0;
        }
#ifdef RASTER_WIDE
        words[24] = float_bits(box.first_column);  // wide (grid.h): float32 columns
        words[25] = float_bits(box.last_column + 1);
#else
        words[24] = half(box.first_column);
        words[25] = half(box.last_column + 1);
#endif
        words[26] = box.first_row;
        words[27] = box.last_row;
        words[28] = float_bits(triangle);
        words[29] = 0;
        words[30] = 0;
        words[31] = 0;
    }

    uint32_t* cb_ptr(uint32_t cb) {
        return reinterpret_cast<uint32_t*>(get_local_cb_interface(cb).fifo_wr_ptr << 4);
    }

}  // namespace setup_k
