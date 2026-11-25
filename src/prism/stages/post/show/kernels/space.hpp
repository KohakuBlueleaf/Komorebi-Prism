// SHOW's part of the command space (prism.core.fields, layout "show"): its address is
// the space's base (get_write_ptr) and the part's byte, a define of the build.
#pragma once

#include <stdint.h>

namespace show_space {

    // The converted pages, the profile page, the buckets (show.h kShowScratchPages).
    constexpr uint32_t scratch(uint32_t base) {
        return base + PRISM_SPACE_SHOW_SCRATCH_AT;
    }

}  // namespace show_space
