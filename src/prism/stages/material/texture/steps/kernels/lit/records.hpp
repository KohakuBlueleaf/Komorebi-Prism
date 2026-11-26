// The lit material's records on the pack CPU (pack/lit/records.hpp's on the step's
// counters): each record that wins a pixel fills its slot once, then keys its normal's
// and specular's texels and its albedo's (and mask's).
#pragma once

#include <stdint.h>

#include "../../../kernels/pack/keys.hpp"
#include "../../../kernels/pack/lit/slot.hpp"
#include "../../../kernels/pack/lit/winners.hpp"
#include "../counters.hpp"

namespace shade_k {

    // A texture's level's numbers (record_numbers): false without that texture.
    inline bool texture_numbers(
        const uint32_t* entry_words,
        uint32_t entries,
        uint32_t entry_base,
        uint32_t level,
        uint32_t* numbers
    ) {
        if (entry_base == 0 || entry_base - 1 + level >= entries) {
            return false;
        }
        const uint32_t* entry = entry_words + kEntryWords * (entry_base - 1 + level);
        const uint32_t width = entry[1] & 0xFFFF, height = entry[1] >> 16;
        if (width == 0 || height == 0) {
            return false;
        }
        numbers[kConstW] = float_bits(width);
        numbers[kConstWLast] = float_bits(width - 1);
        numbers[kConstH] = float_bits(height);
        numbers[kConstHLast] = float_bits(height - 1);
        numbers[kConstAcross] = float_bits((width + 31) / 32);
        numbers[kConstFirst] = float_bits(entry[0] + 1);
        return true;
    }

    // The albedo's mode of a record (its numbers in `numbers`): flat without a texture;
    // merging, a masked material's mask at the same level and sizes keyed too.
    inline Mode albedo_mode(
        const Table& table,
        const uint32_t* material_at,
        uint32_t level,
        bool merging,
        uint32_t* numbers
    ) {
        const uint32_t entry_base = material_at[0] >> 8;
        if (!texture_numbers(
                table.entry_words, table.entries, entry_base, level, numbers
            )) {
            return kFlat;
        }
        const uint32_t* entry = table.entry_words +
            kEntryWords * (entry_base - 1 + level);
        const uint32_t mask_base = material_at[kMaterialMask];
        if (!merging || (material_at[0] & 0xFF) != kKindMasked || mask_base == 0 ||
            mask_base - 1 + level >= table.entries) {
            return kLightTexture;
        }
        const uint32_t* mask_entry = table.entry_words +
            kEntryWords * (mask_base - 1 + level);
        if (mask_entry[1] != entry[1]) {
            return kLightTexture;
        }
        const int32_t pages_on = static_cast<int32_t>(mask_entry[0] - entry[0]);
        numbers[kConstMask] =
            (float_bits(static_cast<uint32_t>(pages_on < 0 ? -pages_on : pages_on)) |
             (pages_on < 0 ? 0x80000000u : 0u));
        return kLightTextureMask;
    }

    // An item's records into Dst rows [first_row, end_row) of `tile_y`'s tile: each
    // winner's slot, the keys of its three textures; false when the list gave up.
    template <typename List>
    inline bool lit_records(
        List& list,
        const Table& table,
        Winners& winners,
        const float* cam,
        uint32_t records,
        int32_t first_row,
        int32_t end_row,
        uint32_t tile_y,
        bool merging,
        Counters& counters
    ) {
        uint32_t* values = counters.values;
        for (uint32_t record_index = 0; record_index < records; ++record_index) {
            const volatile uint32_t* record = list.next();
            if (record == nullptr) {
                return false;
            }
            const uint32_t triangle = record[kRecTri];
            const uint32_t slot = winners.find(triangle, false);
            const uint32_t shade_word = record[kRecShade];
            const uint32_t material = shade_word & 0xFFFF;
            const int32_t box_first = static_cast<int32_t>(record[kRecY0]) -
                32 * tile_y;
            const int32_t box_last = static_cast<int32_t>(record[kRecY1]) - 32 * tile_y;
            const int32_t row_first = box_first < first_row ? first_row : box_first;
            const int32_t row_last = box_last > end_row - 1 ? end_row - 1 : box_last;
            if (slot == kLitSlotEmpty || material >= table.materials ||
                row_first > row_last) {
                continue;  // wins no pixel of the item, or no material
            }
            const uint32_t* material_at = table.material_words +
                kMaterialWords * material;
            uint32_t* slot_at = winners.words + kLitSlotWords * slot;
            uint32_t numbers[kRecordNumbers] = {};
            numbers[kConstTri] = triangle;
            if (slot_at[0] == kSlotUnfilled) {
                fill_slot(
                    slot_at,
                    record,
                    material,
                    material_at,
                    cam,
                    (shade_word & kShadeNoFrame) == 0 &&
                        texture_numbers(
                            table.entry_words,
                            table.entries,
                            material_at[kMaterialNormal],
                            shade_word >> kShadeNormalLevelShift & 0xF,
                            numbers
                        )
                );
            }
            // the normal's and specular's keys (none: the white texel), then the
            // albedo's (and mask's), which marks the pixels
            const bool bent = (slot_at[7] | slot_at[8] | slot_at[9]) != 0;
            const bool shiny = (slot_at[4] | slot_at[5] | slot_at[6]) != 0;
            for (uint32_t texture = 0; texture < 2; ++texture) {
                const bool used = texture == 0 ? bent : shiny;
                const uint32_t shift = texture == 0 ? kShadeNormalLevelShift
                                                    : kShadeSpecularLevelShift;
                if (used &&
                    texture_numbers(
                        table.entry_words,
                        table.entries,
                        material_at[texture == 0 ? kMaterialNormal : kMaterialSpecular],
                        shade_word >> shift & 0xF,
                        numbers
                    )) {
                    record_numbers(numbers);
                    for (int32_t r = row_first; r <= row_last; ++r) {
                        record_row(
                            r,
                            kLightTexture,
                            texture == 0 ? kVecRed : kVecGreen,
                            false,
                            false
                        );
                    }
                }
            }
            const Mode mode = albedo_mode(
                table,
                material_at,
                shade_word >> kShadeLevelShift & 0xF,
                merging,
                numbers
            );
            record_numbers(numbers);
            for (int32_t r = row_first; r <= row_last; ++r) {
                record_row(r, mode, kVecDepth, false, true);
                values[kShadeProfRows]++;
            }
            values[kShadeProfRecords]++;
        }
        return true;
    }

}  // namespace shade_k
