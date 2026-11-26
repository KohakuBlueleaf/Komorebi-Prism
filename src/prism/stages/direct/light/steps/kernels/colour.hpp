// The light step on the pack CPU: a quarter tile's colour by the form and terms (glass,
// the field, the taps, the point alone), its page passes asked through the loop's
// request rings (the material step's request_passes); pack/quarter.hpp's glass_quarter
// and quarter_colour on those rings, adapted.
#pragma once

#include <stdint.h>

#include "../../../../material/texture/steps/kernels/requests.hpp"
#include "planes.hpp"

namespace light_step {

    // A form's state: the command's arithmetic state (pack/passes.hpp) and where its
    // pages come from and go.
    struct LitPass {
        Pass pass;
        material_step::Requests requests;
    };

    // Rows [first, end) of the quarter in page passes of `scan` and `gather`, counted
    // in `counts`. False: gave up.
    template <typename Scan, typename Gather>
    inline bool lit_passes(LitPass& lit, PassCounts& counts, Scan scan, Gather gather) {
        Pass& pass = lit.pass;
        return material_step::request_passes(
            pass.waits,
            lit.requests,
            pass.first,
            pass.end,
            pass.pages,
            counts,
            scan,
            gather
        );
    }

    // glass keys, shadow and reflection texels, colour
    __attribute__((noinline)) bool lit_glass_quarter(LitPass& lit, bool field) {
        Pass& pass = lit.pass;
        pass.values[kLightProfGlassQuarters]++;
        pass.keys<true>();
        const uint32_t terms = pass.numbers.terms;
        if ((terms & kTermShadow) != 0 &&
            !lit_passes(
                lit,
                pass.counts,
                ScanTaps{pass, 0, kLightKeys},
                GatherTaps{pass, 0, kLightKeys, false}
            )) {
            return false;
        }
        if ((terms & kTermBackground) != 0 &&
            !lit_passes(
                lit,
                pass.counts,
                ScanTaps{pass, kLightKeys, kLightKeys + kGlassKeys},
                GatherTaps{pass, kLightKeys, kLightKeys + kGlassKeys, false}
            )) {
            return false;
        }
        if (field) {  // the field at the glass point, then the colour
            return lit_passes(lit, pass.field_counts, FieldScan{pass}, FieldRows{pass});
        }
        for (uint32_t r = pass.first; r < pass.end; ++r) {
            light_row<true>(r - pass.row0, pass.numbers, pass.values);
            pass.values[kLightProfRows]++;
        }
        return true;
    }

    // The quarter's colour into Dst's albedo rows; false: gave up.
    inline bool lit_quarter(
        LitPass& lit, bool in_front, bool keyed, bool pointed, bool field
    ) {
        Pass& pass = lit.pass;
        if (pass.glass && !in_front) {  // C toned, no light
            tone_rows(
                pass.first - pass.row0,
                pass.end - pass.row0,
                pass.table,
                pass.numbers.graded
            );
            tensix_sync();
            pass.now = km::wall();
            pass.values[kLightProfMath] += pass.now - pass.mark;
            return true;
        }
        if (pass.glass) {
            return lit_glass_quarter(lit, field);
        }
        if (field) {
            // keys and the point; the shadow's and background's texels; then the
            // field's pages, texels and each row's colour
            pass.keys();
            return (!keyed ||
                    lit_passes(
                        lit,
                        pass.counts,
                        ScanTaps{pass, 0, kLightKeys},
                        GatherTaps{pass, 0, kLightKeys, false}
                    )) &&
                lit_passes(lit, pass.field_counts, FieldScan{pass}, FieldRows{pass});
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
        return lit_passes(
            lit,
            pass.counts,
            ScanTaps{pass, 0, kLightKeys},
            GatherTaps{pass, 0, kLightKeys, true}
        );
    }

}  // namespace light_step
