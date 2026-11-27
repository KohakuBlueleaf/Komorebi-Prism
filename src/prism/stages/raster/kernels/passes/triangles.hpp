// The vector unit's part of COUNT and SETUP, continued: box, area, edges, planes,
// the lanes' flags and records, and their copies out of the window.
#pragma once

#include "vector.hpp"

namespace setup_k {

    namespace setup_pass {

        // Box of `coordinate` (0: x, 1: y) to words kRawX0 + 2 c, kRawX1 + 2 c:
        // ceil(lo - 0.5) in [0, size], floor(hi - 0.5) in [-1, size - 1].
        inline void box(uint32_t coordinate, uint32_t size_bits, uint32_t last_bits) {
            load(L0, kSlotScreen + coordinate);
            load(L1, kSlotScreen + 3 + coordinate);
            load(L2, kSlotScreen + 6 + coordinate);
            order_pair(L1, L0);
            order_pair(L2, L0);
            order_pair(L1, L2);
            immediate(L7, 0x3F000000);  // 0.5
            sub(L0, L7, L0);
            sub(L1, L7, L2);
            round_box(
                0xBF000000, size_bits, true, kSlotRecords + kRawX0 + 2 * coordinate
            );
            TT_SFPMOV(0, L2, L0, 0);
            round_box(
                0xBF800000, last_bits, false, kSlotRecords + kRawX1 + 2 * coordinate
            );
        }

        // The doubled area, raw to kRawArea; corners 1 and 2 swapped where it is
        // negative (their screen numbers and colours), the area then made positive.
        inline void area_and_order() {
            load(L0, kSlotScreen + 3);
            load(L1, kSlotScreen);
            sub(L0, L1, L2);  // x1 - x0
            load(L0, kSlotScreen + 7);
            load(L3, kSlotScreen + 1);
            sub(L0, L3, L4);  // y2 - y0
            mul(L2, L4, L2);
            load(L0, kSlotScreen + 6);
            sub(L0, L1, L4);  // x2 - x0
            load(L0, kSlotScreen + 4);
            sub(L0, L3, L5);  // y1 - y0
            mul(L4, L5, L4);
            sub(L2, L4, L2);
            store(L2, kSlotRecords + kRawArea);
            TTI_SFPNOP;
            TTI_SFPPUSHC(0, 0, 0, 0);
            TTI_SFPSETCC(0, L2, 0, kLt0);
            for (uint32_t j = 0; j < 3; ++j) {
                load(L0, kSlotScreen + 3 + j);
                load(L1, kSlotScreen + 6 + j);
                store(L1, kSlotScreen + 3 + j);
                store(L0, kSlotScreen + 6 + j);
                load(L0, kSlotColour + 3 + j);
                load(L1, kSlotColour + 6 + j);
                store(L1, kSlotColour + 3 + j);
                store(L0, kSlotColour + 6 + j);
            }
            neg(L2, L2);
            TTI_SFPPOPC(0, 0, 0, 0);
            store(L2, kSlotArea);
        }

        // Edge `edge` between corners p and q: a = y_p - y_q, b = x_q - x_p, c = -(a
        // x_p + b y_p), to record words k, 3 + k, 6 + k.
        inline void edges() {
            constexpr uint32_t pq[3][2] = {{1, 2}, {2, 0}, {0, 1}};
            for (uint32_t edge = 0; edge < 3; ++edge) {
                const uint32_t p = kSlotScreen + 3 * pq[edge][0];
                const uint32_t q = kSlotScreen + 3 * pq[edge][1];
                load(L0, p);
                load(L1, p + 1);
                load(L2, q);
                load(L3, q + 1);
                sub(L1, L3, L4);  // a
                sub(L2, L0, L5);  // b
                store(L4, kSlotRecords + edge);
                store(L5, kSlotRecords + 3 + edge);
                mul(L4, L0, L4);
                mul(L5, L1, L5);
                add(L4, L5, L4);
                TTI_SFPNOP;
                neg(L4, L4);
                store(L4, kSlotRecords + 6 + edge);
            }
        }

        // Per-corner values in slots first_slot + {0, 1, 2} x step: for each of a, b,
        // c,
        // ((c0 v0 + c1 v1) + c2 v2) / area to record word first_word + coefficient.
        inline void plane(uint32_t first_slot, uint32_t step, uint32_t first_word) {
            for (uint32_t coefficient = 0; coefficient < 3; ++coefficient) {
                load(L0, kSlotRecords + 3 * coefficient);
                load(L1, first_slot);
                mul(L0, L1, L2);
                load(L0, kSlotRecords + 3 * coefficient + 1);
                load(L1, first_slot + step);
                mul(L0, L1, L3);
                add(L2, L3, L2);
                load(L0, kSlotRecords + 3 * coefficient + 2);
                load(L1, first_slot + 2 * step);
                mul(L0, L1, L3);
                add(L2, L3, L2);
                load(L4, kSlotInverseArea);
                mul(L2, L4, L2);
                store(L2, kSlotRecords + first_word + coefficient);
            }
        }

        // As plane, of the values less `origin_bits` (L5), added back to the constant.
        inline void plane_from(
            uint32_t first_slot,
            uint32_t step,
            uint32_t first_word,
            uint32_t origin_bits
        ) {
            immediate(L5, origin_bits);
            for (uint32_t coefficient = 0; coefficient < 3; ++coefficient) {
                load(L0, kSlotRecords + 3 * coefficient);
                load(L1, first_slot);
                sub(L1, L5, L1);
                mul(L0, L1, L2);
                load(L0, kSlotRecords + 3 * coefficient + 1);
                load(L1, first_slot + step);
                sub(L1, L5, L1);
                mul(L0, L1, L3);
                add(L2, L3, L2);
                load(L0, kSlotRecords + 3 * coefficient + 2);
                load(L1, first_slot + 2 * step);
                sub(L1, L5, L1);
                mul(L0, L1, L3);
                add(L2, L3, L2);
                load(L4, kSlotInverseArea);
                mul(L2, L4, L2);
                if (coefficient == 2) {
                    add(L2, L5, L2);
                }
                store(L2, kSlotRecords + first_word + coefficient);
            }
        }

        // The float32 bits of an integer n in [1, 2^24).
        inline uint32_t float_bits(uint32_t n) {
            const uint32_t exponent = 31 - __builtin_clz(n);
            return (127 + exponent) << 23 | (n << (23 - exponent) & 0x7FFFFF);
        }

        // A block's screen, area, box (in `grid`'s padded frame), distances, `planes`
        // edges and planes; `weighted` (shaded) first multiplies corner values by 1/z;
        // the 1/z plane from 1/z less `depth_origin` (bits, 0: none).
        inline void triangles(
            bool planes,
            Grid grid = {kGridDefault, kGridDefault},
            bool weighted = false,
            uint32_t depth_origin = 0
        ) {
            screen();
            area_and_order();
            const uint32_t width = 32 * grid.across, height = 32 * grid.down;
            box(0, float_bits(width), float_bits(width - 1));  // 1024, 1023 by default
            box(1, float_bits(height), float_bits(height - 1));
            for (uint32_t corner = 0; corner < 3; ++corner) {
                load(L0, kSlotCameraSpace + 3 * corner + 2);
                store(L0, kSlotRecords + kRawZ + corner);
            }
            if (!planes) {
                return;
            }
            edges();
            load(L0, kSlotArea);
            recip(L0, L1, L2, L3, L4, L5);
            store(L1, kSlotInverseArea);
            if (depth_origin != 0) {
                plane_from(kSlotScreen + 2, 3, 12, depth_origin);
            } else {
                plane(kSlotScreen + 2, 3, 12);
            }
            if (weighted) {
                for (uint32_t corner = 0; corner < 3; ++corner) {
                    load(L1, kSlotScreen + 3 * corner + 2);
                    for (uint32_t channel = 0; channel < 3; ++channel) {
                        load(L0, kSlotColour + 3 * corner + channel);
                        mul(L0, L1, L0);
                        store(L0, kSlotColour + 3 * corner + channel);
                    }
                }
            }
            for (uint32_t channel = 0; channel < 3; ++channel) {
                plane(kSlotColour + channel, 3, 15 + 3 * channel);
            }
        }

        // The integer n of a box word 1.5 x 2^23 + n into `integer` (L4 holds the
        // magic).
        inline void box_integer(uint32_t raw, uint32_t integer) {
            TT_SFPMOV(0, L4, integer, 0);
            TT_SFPIADD(0, raw, integer, kIaddSubtract | kCcNone);
        }

        // float16 bits of the integer n in [0, 2048) whose float32 is in `number` (L5
        // holds 0x1C000): (bits >> 13) - 0x1C000, and 0 for n = 0.
        inline void half_of(uint32_t number, uint32_t work) {
            TTI_SFPNOP;  // number may come from a multiply-add; SFPSHFT reads VD unseen
            TT_SFPMOV(0, number, work, 0);
            TT_SFPGT(0, ZERO, work, kSetVd);  // n > 0
            TT_SFPSHFT((-13) & 0xFFF, 0, number, kShiftImmediate);
            TT_SFPMOV(0, L5, L6, 0);
            TT_SFPIADD(0, number, L6, kIaddSubtract | kCcNone);
            TT_SFPAND(0, work, L6, 0);
        }

        // Per lane: kept and crossing flags, box as integers and float16 columns; with
        // `records` the thresholds, triangle word (first_word + lane), words 29 to 31
        // as 0.
        inline void finish_lanes(bool records, uint32_t first_word) {
            // beyond the near distance, per corner (float order, near > 0)
            load(L7, kSlotCamera + 15);
            load(L0, kSlotRecords + kRawZ);
            TT_SFPGT(0, L7, L0, kSetVd);
            load(L1, kSlotRecords + kRawZ + 1);
            TT_SFPGT(0, L7, L1, kSetVd);
            load(L2, kSlotRecords + kRawZ + 2);
            TT_SFPGT(0, L7, L2, kSetVd);
            TT_SFPMOV(0, L0, L3, 0);
            TT_SFPAND(0, L1, L3, 0);
            TT_SFPAND(0, L2, L3, 0);  // L3: every corner beyond
            TT_SFPOR(0, L1, L0, 0);
            TT_SFPOR(0, L2, L0, 0);
            TT_SFPXOR(0, L3, L0, 0);  // L0: some but not all beyond (crossing)
            immediate(L6, 0x7FFFFFFF);
            load(L1, kSlotRecords + kRawArea);
            TT_SFPAND(0, L6, L1, 0);
            TT_SFPGT(0, ZERO, L1, kSetVd);  // a non-zero area
            TT_SFPAND(0, L1, L3, 0);
            load(L1, kSlotRecords + kRawX0);
            load(L2, kSlotRecords + kRawX1);
            TT_SFPLE(0, L2, L1, kSetVd);  // x0 <= x1 (box words ordered as numbers)
            TT_SFPAND(0, L1, L3, 0);
            load(L1, kSlotRecords + kRawY0);
            load(L2, kSlotRecords + kRawY1);
            TT_SFPLE(0, L2, L1, kSetVd);
            TT_SFPAND(0, L1, L3, 0);
            TT_SFPSHFT((-31) & 0xFFF, 0, L3, kShiftImmediate);  // kept: 1
            TT_SFPSHFT((-31) & 0xFFF, 0, L0, kShiftImmediate);
            TT_SFPSHFT(1, 0, L0, kShiftImmediate);  // crossing: 2
            TT_SFPOR(0, L0, L3, 0);
            store(L3, kSlotFlags);
            // the box: rows as integers in place, columns as integers aside
            immediate(L4, kMagic);
            load(L0, kSlotRecords + kRawY0);
            box_integer(L0, L1);
            store(L1, kSlotRecords + kRawY0);
            load(L0, kSlotRecords + kRawY1);
            box_integer(L0, L1);
            store(L1, kSlotRecords + kRawY1);
            load(L0, kSlotRecords + kRawX0);
            box_integer(L0, L1);
            store(L1, kSlotFirstColumn);
            load(L2, kSlotRecords + kRawX1);
            box_integer(L2, L3);
            store(L3, kSlotLastColumn);
            if (!records) {
                return;
            }
#ifdef RASTER_WIDE
            // columns x0 and x1 + 1 as float32 (wide, grid.h; L0: x0's word, L2: x1's)
            sub(L0, L4, L0);
            store(L0, kSlotRecords + kRawX0);
            add(L2, ONE, L2);
            sub(L2, L4, L2);
            store(L2, kSlotRecords + kRawX1);
#else
            // columns x0 and x1 + 1 as float16 (L0: x0's word, L2: x1's word)
            immediate(L5, 0x1C000);
            sub(L0, L4, L0);
            half_of(L0, L1);
            store(L6, kSlotRecords + kRawX0);
            add(L2, ONE, L2);
            sub(L2, L4, L2);
            half_of(L2, L1);
            store(L6, kSlotRecords + kRawX1);
#endif
            // top-left thresholds: a > 0, or a = +-0 and b > 0
            immediate(L7, 0x80000001);
            immediate(L6, 0x7FFFFFFF);
            for (uint32_t corner = 0; corner < 3; ++corner) {
                load(L0, kSlotRecords + corner);
                load(L1, kSlotRecords + 3 + corner);
                TT_SFPMOV(0, L0, L2, 0);
                TT_SFPGT(0, ZERO, L2, kSetVd);  // a > +0
                TT_SFPAND(0, L6, L0, 0);
                TT_SFPLE(0, ZERO, L0, kSetVd);  // |a| <= +0: a is a zero
                TT_SFPGT(0, ZERO, L1, kSetVd);  // b > +0
                TT_SFPAND(0, L1, L0, 0);
                TT_SFPOR(0, L2, L0, 0);
                TT_SFPAND(0, L7, L0, 0);
                store(L0, kSlotRecords + 9 + corner);
            }
            // triangle word (first_word + lane, as integers), then words 29 to 31
            load(L0, kSlotLaneNumber);
            immediate(L1, first_word);
            TT_SFPIADD(0, L0, L1, kCcNone);
            store(L1, kSlotRecords + 28);
            TT_SFPMOV(0, ZERO, L0, 0);
            store(L0, kSlotRecords + 29);
            store(L0, kSlotRecords + 30);
            store(L0, kSlotRecords + 31);
        }

        // Slots first_slot (even) on, 2 count of them, as window pairs (slot 2 j + s,
        // lane l at 64 j + 2 l + s): unit-stride copies, about 1 cycle a word
        // against 6.
        inline void pairs_out(uint32_t first_slot, uint32_t count, uint32_t* words) {
            const volatile uint32_t* source = window() + word(first_slot);
#if defined(__riscv_vector)
            const size_t vector_length = __riscv_vsetvl_e32m8(32);
            for (uint32_t i = 0; i < 64 * count; i += 32) {
                __riscv_vse32_v_u32m8(
                    words + i,
                    __riscv_vle32_v_u32m8(
                        const_cast<const uint32_t*>(source + i), vector_length
                    ),
                    vector_length
                );
            }
            asm volatile("" ::: "memory");
#else
            for (uint32_t i = 0; i < 64 * count; ++i) {
                words[i] = source[i];
            }
#endif
        }

        // Lane `lane`'s record (32 words) out of 16 pairs copied by pairs_out, to
        // `record`.
        inline void lane_record(
            const uint32_t* pairs, uint32_t lane, uint32_t* record
        ) {
#if defined(__riscv_vector)
            const size_t vector_length = __riscv_vsetvl_e32m4(16);
            const auto pair_values = (__riscv_vlsseg2e32_v_u32m4x2(
                pairs + 2 * lane, 256, vector_length
            ));
            __riscv_vsseg2e32_v_u32m4x2(record, pair_values, vector_length);
            asm volatile("" ::: "memory");
#else
            for (uint32_t word_index = 0; word_index < 32; ++word_index) {
                record[word_index] = (pairs
                                          [64 * (word_index >> 1) + 2 * lane +
                                           (word_index & 1)]);
            }
#endif
        }

    }  // namespace setup_pass

}  // namespace setup_k
