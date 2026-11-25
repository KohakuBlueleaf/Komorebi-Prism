// SETUP on a shaded frame: a record's shade word (setup.h kRecShadeWord) from its
// triangle's words of the shade block, beside the mesh block.
#pragma once

#include <stdint.h>

#include "../common/layouts.hpp"

namespace setup_k {

    // A shaded record's word from the triangle's shade words (32 apart); a level = #k
    // < levels with texels > area 2^(2k - 1), as integers.
    inline uint32_t shade_word(uint32_t area_bits, const uint32_t* shade) {
        const uint32_t material = shade[32];
        uint32_t word = material & (0xFFFF | kShadeWordKept);
        // The level: the most k < levels with texels_bits > area_bits + (2k - 1) << 23
        // (int32; 0x7F800000 once its exponent reaches 255), the old loop's count
        const int32_t area = static_cast<int32_t>(area_bits);
        // k whose threshold is not 0x7F800000: (area's exponent) + 2k - 1 < 255
        const int32_t finite = area < 0 ? 0 : (255 - (area >> 23)) >> 1;
        for (uint32_t texture = 0; texture < 3; ++texture) {
            const int32_t
                top = (static_cast<int32_t>(material >> (16 + 4 * texture) & 0xF) - 1);
            const int32_t texels = (static_cast<int32_t>(
                shade[texture == 0 ? 0 : 32 + 32 * texture]
            ));
            int32_t level = 0;
            if (top > 0) {
                if (texels > 0x7F800000) {  // over every threshold
                    level = top;
                } else if (area >= 0 && texels > area) {
                    // (2k - 1) << 23 < texels - area
                    level = (((texels - area - 1) >> 23) + 1) >> 1;
                    level = level < finite ? level : finite;
                    level = level < top ? level : top;
                }
            }
            word |= static_cast<uint32_t>(level) << (16 + 4 * texture);
        }
        return word;
    }

}  // namespace setup_k
