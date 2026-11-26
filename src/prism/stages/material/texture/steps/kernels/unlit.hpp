// The unlit material of one layer of a tile on the pack CPU, its planes in L1: u, v and
// the colour divided by 1/z, its records' texel keys as the pass streams them, the page
// passes and texels, the colour; a merging layer's colour (masked: where it takes, with
// the merged 1/z; glass: blended) into the opaque layer's pages.
#pragma once

#include <stdint.h>

#include "../../../../raster/steps/kernels/lists.hpp"
#include "../../kernels/pack/blend.hpp"
#include "../../kernels/pack/colour.hpp"
#include "planes.hpp"
#include "run.hpp"
#include "texels.hpp"

namespace material_step {

    // The layer's records as `list` streams them into Dst rows of the band: their keys,
    // colours and marks (pack/pack.hpp's item_records on a stream); false: gave up.
    template <typename List>
    inline bool unlit_records(List& list, Run& run, bool merging, bool glass) {
        while (const volatile uint32_t* record = list.next()) {
            const uint32_t shade_word = record[kRecShade];
            const uint32_t material = shade_word & 0xFFFF;
            const uint32_t level = shade_word >> kShadeLevelShift & 0xF;
            const int32_t box_first = static_cast<int32_t>(record[kRecY0]) -
                32 * static_cast<int32_t>(run.tile_y);
            const int32_t box_last = static_cast<int32_t>(record[kRecY1]) -
                32 * static_cast<int32_t>(run.tile_y);
            const int32_t row_first = box_first < run.first_row ? run.first_row
                                                                : box_first;
            const int32_t row_last = box_last > run.end_row - 1 ? run.end_row - 1
                                                                : box_last;
            if (material >= run.table.materials || row_first > row_last) {
                continue;  // no material: FILL's colour divided by 1/z (flat)
            }
            uint32_t numbers[kRecordNumbers];
            const Mode mode = record_mode(
                run.table, record[kRecTri], material, level, merging, numbers
            );
            if (mode == kFlat) {
                continue;  // FILL's colour divided by 1/z, no texel
            }
            record_numbers(numbers);
            // the glass layer's pixels keep their material for the blend
            const uint32_t mark_bits = glass ? kMinusTwo | material : kMinusTwo;
            for (int32_t r = row_first; r <= row_last; ++r) {
                record_row(r, mode, kVecDepth, true, true, mark_bits);
                run.counters.values[kShadeProfRows]++;
            }
            run.counters.values[kShadeProfRecords]++;
        }
        return list.end_walk();
    }

    // One layer (`role`, `mode` its kShade* bits) of the band: its planes at `plane`,
    // the opaque layer's at `opaque` (the result's pages). False: gave up (recorded).
    template <typename List>
    inline bool unlit_layer(
        List& list, Run& run, Role role, uint32_t mode, uint32_t plane, uint32_t opaque
    ) {
        const bool merging = role != kOpaque;
        const bool glass = role == kGlass;
        const bool merged_depth = role == kMasked && (mode & kShadeMergedDepth) != 0;
        const uint32_t* plane_words = reinterpret_cast<const uint32_t*>(plane);
        const uint32_t* opaque_words = reinterpret_cast<const uint32_t*>(opaque);
        planes_in(
            plane_words, opaque_words, run.first_row, run.end_row, merging, run.vl
        );
        for (int32_t r = run.first_row; r < run.end_row; ++r) {
            divide_row(r);
        }
        if (!unlit_records(list, run, merging, glass)) {
            return false;
        }
        tensix_sync();
        if (!texels(
                run.waits,
                run.requests,
                run.first_row,
                run.end_row,
                run.index,
                run.pages,
                run.table.gamma,
                run.slots_address,
                run.table.page_limit,
                merging && !glass,  // the masks' (the glass layer has none)
                run.counters
            )) {
            return false;
        }
        colour_rows(run.first_row, run.end_row);
        // the opaque layer's colour pages; a merging layer's own pages 1 to 4 first
        const uint32_t out = (merging ? plane : opaque) + kOutPageBytes;
        colour_out(out, run.first_word, run.words);
        if (glass) {  // tau C + (1 - max tau) colour where marked, else C
            glass_blend(
                out,
                opaque_words,
                run.table.material_words,
                run.first_word,
                run.words,
                run.vl
            );
        } else if (merging) {  // the opaque layer's colour where the depth row is not 1
            masked_merge(
                out,
                plane_words,
                opaque_words,
                run.first_word,
                run.words,
                merged_depth,
                run.vl
            );
        }
        if (merging) {
            for (uint32_t page = 0; page < kShadeColourPages; ++page) {
                copy_page_rows(
                    opaque,
                    kShadeFirstPlane + page,
                    out,
                    page,
                    run.first_word,
                    run.words,
                    run.vl
                );
            }
            if (merged_depth) {  // the merged 1/z: the out item's fourth page
                copy_page_rows(
                    opaque, 0, out, kShadeColourPages, run.first_word, run.words, run.vl
                );
            }
        }
        landed(
            opaque +
            4 * (kShadeColourPages * kPlaneWords + run.first_word + run.words - 1)
        );
        run.counters.values[kShadeProfTiles]++;
        return true;
    }

}  // namespace material_step
