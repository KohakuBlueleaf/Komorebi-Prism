// SHADE's and LIGHT's parts of the command space (prism.core.fields, layout "texel"):
// a part's address is the space's base on this CPU (a mover's get_write_ptr, compute's
// compute_mail::write_ptr) and the part's byte, a define of the build.
#pragma once

#include <stdint.h>

namespace texel_space {

    // The texel pages' slots (and the page after them).
    constexpr uint32_t texel_slots(uint32_t base) {
        return base + PRISM_SPACE_TEXEL_SLOTS_AT;
    }

    // The pack CPU's work.
    constexpr uint32_t pack_work(uint32_t base) {
        return base + PRISM_SPACE_PACK_WORK_AT;
    }

    // The page passes' hash.
    constexpr uint32_t texel_work(uint32_t base) {
        return base + PRISM_SPACE_TEXEL_WORK_AT;
    }

}  // namespace texel_space
