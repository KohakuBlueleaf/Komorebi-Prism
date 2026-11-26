// The material step's layers on every compute CPU: each layer's role and kShade* bits
// from the step's words, and the order the step walks them (the list pass's).
#pragma once

#include <stdint.h>

#include "../../../../../core/include/thread/frame.h"
#include "../../../../../core/include/thread/record.h"
#include "../../kernels/shade.h"
#include "material_words.h"

namespace material_step {

    // A layer's part in the step: not shaded, the opaque layer (shaded in its own
    // planes), merged into it (masked), blended over it (glass; lit: its own surface).
    enum Role : uint32_t { kNone, kOpaque, kMasked, kGlass };

    // Layer `layer`'s role and kShade* bits from the step's word `layers`.
    inline Role role_of(uint32_t layers, uint32_t layer, uint32_t& mode) {
        const uint32_t bits = MATERIAL_LAYER(layers, layer);
        mode = bits >> MATERIAL_MODE_SHIFT;
        if ((bits & MATERIAL_SHADED) == 0) {
            return kNone;
        }
        if ((mode & kShadeGlass) != 0) {
            return kGlass;
        }
        return (bits & MATERIAL_MERGING) != 0 ? kMasked : kOpaque;
    }

    // The layers in the order the step walks them (opaque, masked, glass), as the list
    // pass streams them; `count` of them, the opaque layer's index (TR_LAYERS: none).
    struct Order {
        uint32_t layer[TR_LAYERS];
        Role role[TR_LAYERS];
        uint32_t mode[TR_LAYERS];
        uint32_t count = 0, opaque = TR_LAYERS;

        Order(const volatile uint32_t* page, uint32_t layers_word) {
            const uint32_t layers = page[TF_LAYER_COUNT] < TR_LAYERS
                ? page[TF_LAYER_COUNT]
                : TR_LAYERS;
            for (uint32_t wanted = kOpaque; wanted <= kGlass; ++wanted) {
                for (uint32_t index = 0; index < layers; ++index) {
                    uint32_t bits = 0;
                    if (role_of(layers_word, index, bits) != wanted) {
                        continue;
                    }
                    layer[count] = index;
                    role[count] = static_cast<Role>(wanted);
                    mode[count] = bits;
                    opaque = wanted == kOpaque && opaque == TR_LAYERS ? index : opaque;
                    ++count;
                }
            }
        }
    };

}  // namespace material_step
