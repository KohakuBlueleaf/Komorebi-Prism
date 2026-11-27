// SHADE's texture keys of a record: its material's kind and texture from the table, the
// level's entry, the numbers the vector unit keys its pixels' texels with.
#pragma once

#include <stdint.h>

#include "rows.hpp"

namespace shade_k {

    // SHADE's table in L1: its counts and the parts the pack thread reads.
    struct Table {
        const uint32_t* words = nullptr;
        uint32_t materials = 0, entries = 0, page_limit = 0;
        const uint32_t* gamma = nullptr;
        const uint32_t* material_words = nullptr;
        const uint32_t* entry_words = nullptr;

        // The table at `address` (0: none); false when none or its words do not fit.
        bool at(uint32_t address) {
            words = reinterpret_cast<const uint32_t*>(address);
            materials = address ? words[kTabMaterials] : 0;
            entries = address ? words[kTabEntries] : 0;
            page_limit = address ? words[kTabPages] : 0;
            gamma = words + kTabGamma;
            material_words = words + kTabMaterial;
            entry_words = material_words + kMaterialWords * materials;
            return address != 0 &&
                kTabMaterial + kMaterialWords * materials + kEntryWords * entries <=
                kShadeTableBytes / 4;
        }
    };

    // The uv map `map` (kMapAlbedo, kMapNormal, kMapSpecular) of a material's row into
    // the numbers from kConstMap; false for the identity (the stored (u, v) as they
    // are).
    inline bool slot_map(const uint32_t* material_at, uint32_t map, uint32_t* numbers) {
        const uint32_t* words = material_at + kMaterialMaps + kMapWords * map;
        constexpr uint32_t kIdentity[kMapWords] = {
            0x3F800000u, 0, 0, 0, 0x3F800000u, 0
        };
        bool identity = true;
        for (uint32_t i = 0; i < kMapWords; ++i) {
            numbers[kConstMap + i] = words[i];
            identity = identity && words[i] == kIdentity[i];
        }
        return !identity;
    }

    // A record's mode and its numbers (kRecordNumbers) from its triangle, `material`
    // and albedo `level`; merging, a masked material's mask at the same level and
    // sizes. kFlat: FILL's colour divided by 1/z, no texel.
    inline Mode record_mode(
        const Table& table,
        uint32_t triangle,
        uint32_t material,
        uint32_t level,
        bool merging,
        uint32_t* numbers
    ) {
        const uint32_t* material_at = table.material_words + kMaterialWords * material;
        const uint32_t kind = material_at[0] & 0xFF;
        const uint32_t entry_base = material_at[0] >> 8;
        const bool emissive = kind == kKindEmissive;
        Mode mode = kind == kKindFlat ? kFlat : emissive ? kEmissive : kLight;
        for (uint32_t i = 0; i < kRecordNumbers; ++i) {
            numbers[i] = 0;
        }
        numbers[kConstTri] = triangle;
        if (kind != kKindFlat && entry_base != 0 &&
            entry_base - 1 + level < table.entries) {
            const uint32_t*
                entry = (table.entry_words + kEntryWords * (entry_base - 1 + level));
            const uint32_t width = entry[1] & 0xFFFF, height = entry[1] >> 16;
            if (width != 0 && height != 0) {
                mode = emissive ? kEmissiveTexture : kLightTexture;
                numbers[kConstW] = float_bits(width);
                numbers[kConstWLast] = float_bits(width - 1);
                numbers[kConstH] = float_bits(height);
                numbers[kConstHLast] = float_bits(height - 1);
                numbers[kConstAcross] = float_bits((width + 31) / 32);
                numbers[kConstFirst] = float_bits(entry[0] + 1);
            }
            // merging, a masked material's mask at the same level and sizes
            const uint32_t mask_base = material_at[kMaterialMask];
            if (merging && mode == kLightTexture && kind == kKindMasked &&
                mask_base != 0 && mask_base - 1 + level < table.entries) {
                const uint32_t* mask_entry =
                    (table.entry_words + kEntryWords * (mask_base - 1 + level));
                if (mask_entry[1] == entry[1]) {
                    const int32_t pages_on = (static_cast<int32_t>(
                        mask_entry[0] - entry[0]
                    ));
                    mode = kLightTextureMask;
                    numbers[kConstMask] =
                        (float_bits(
                             static_cast<uint32_t>(pages_on < 0 ? -pages_on : pages_on)
                         ) |
                         (pages_on < 0 ? 0x80000000u : 0u));
                }
            }
        }
        for (uint32_t channel = 0; channel < 3; ++channel) {
            numbers[kConstBase + channel] = material_at[1 + channel];
        }
        return mode;
    }

}  // namespace shade_k
