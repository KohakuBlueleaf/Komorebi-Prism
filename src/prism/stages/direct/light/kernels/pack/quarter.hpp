// LIGHT on the pack CPU: a quarter tile: its planes into Dst, its colour by the form
// and terms (glass, the field, the taps, the point alone), its colour planes out.
#pragma once

#include <stdint.h>

#include "glass.hpp"
#include "passes.hpp"

namespace light_k {

    // a plane's kLightRows rows are 256 words in its page and in Dst
    constexpr uint32_t kQuarterWords = 32 * kLightRows;

    // The quarter's planes from the item's pages (the ring at `planes`, wrapped at
    // `limit` by `size`) into Dst.
    inline void copy_in(
        uint32_t planes, uint32_t quarter, uint32_t limit, uint32_t size, size_t vl
    ) {
        for (uint32_t plane = 0; plane < kLvPlanes; ++plane) {
            uint32_t page = planes + kLightSource[plane] * kOutPageBytes;
            if (page >= limit) {
                page -= size;
            }
            const uint32_t* from =
                (reinterpret_cast<const uint32_t*>(page) + kQuarterWords * quarter);
            for (uint32_t i = 0; i < kQuarterWords; i += 32) {
                __riscv_vse32_v_u32m8(
                    const_cast<uint32_t*>(window() + kQuarterWords * plane + i),
                    __riscv_vle32_v_u32m8(from + i, vl),
                    vl
                );
            }
        }
        asm volatile("" ::: "memory");
    }

    // glass keys, shadow and reflection texels, colour (out of line: the first
    // command's hot loops stay compact)
    __attribute__((noinline)) bool glass_quarter(Pass& pass, bool field) {
        pass.values[kLightProfGlassQuarters]++;
        pass.keys<true>();
        const uint32_t terms = pass.numbers.terms;
        if ((terms & kTermShadow) != 0 &&
            !passes(
                pass,
                pass.counts,
                ScanTaps{pass, 0, kLightKeys},
                GatherTaps{pass, 0, kLightKeys, false}
            )) {
            return false;
        }
        if ((terms & kTermBackground) != 0 &&
            !passes(
                pass,
                pass.counts,
                ScanTaps{pass, kLightKeys, kLightKeys + kGlassKeys},
                GatherTaps{pass, kLightKeys, kLightKeys + kGlassKeys, false}
            )) {
            return false;
        }
        if (field) {  // the field at the glass point, then the colour
            return passes(pass, pass.field_counts, FieldScan{pass}, FieldRows{pass});
        }
        for (uint32_t r = pass.first; r < pass.end; ++r) {
            light_row<true>(r - pass.row0, pass.numbers, pass.values);
            pass.values[kLightProfRows]++;
        }
        return true;
    }

    // The quarter's colour into Dst's albedo rows; false: gave up.
    inline bool quarter_colour(
        Pass& pass, bool in_front, bool keyed, bool pointed, bool field
    ) {
        uint32_t* values = pass.values;
        if (pass.glass && !in_front) {  // C toned, no light
            tone_rows(
                pass.first - pass.row0,
                pass.end - pass.row0,
                pass.table,
                pass.numbers.graded
            );
            tensix_sync();
            pass.now = km::wall();
            values[kLightProfMath] += pass.now - pass.mark;
            return true;
        }
        if (pass.glass) {
            return glass_quarter(pass, field);
        }
        if (field) {
            // keys and the point; the shadow's and background's texels; then the
            // field's pages, texels and each row's colour
            pass.keys();
            return (!keyed ||
                    passes(
                        pass,
                        pass.counts,
                        ScanTaps{pass, 0, kLightKeys},
                        GatherTaps{pass, 0, kLightKeys, false}
                    )) &&
                passes(pass, pass.field_counts, FieldScan{pass}, FieldRows{pass});
        }
        if (!keyed) {
            if (pointed) {  // the scene point only (keys 0)
                pass.keys();
            }
            return pass.colour(pass.first, pass.end);
        }
        pass.keys();
        // a row's texel addresses (the zero texel where a key is 0), their gather, the
        // rows' colour
        return passes(
            pass,
            pass.counts,
            ScanTaps{pass, 0, kLightKeys},
            GatherTaps{pass, 0, kLightKeys, true}
        );
    }

    // The quarter's colour rows (Dst's albedo planes) to the out pages' planes 1 to 3.
    inline void copy_out(uint32_t out, uint32_t quarter, size_t vl) {
        for (uint32_t channel = 0; channel < kLightColourPlanes; ++channel) {
            uint32_t* to =
                (reinterpret_cast<uint32_t*>(
                     out + (kLightFirstPlane + channel) * kOutPageBytes
                 ) +
                 kQuarterWords * quarter);
            for (uint32_t i = 0; i < kQuarterWords; i += 32) {
                __riscv_vse32_v_u32m8(
                    to + i,
                    __riscv_vle32_v_u32m8(
                        const_cast<const uint32_t*>(
                            window() + kQuarterWords * (kLvAlbedo + channel) + i
                        ),
                        vl
                    ),
                    vl
                );
            }
        }
        asm volatile("" ::: "memory");
    }

}  // namespace light_k
