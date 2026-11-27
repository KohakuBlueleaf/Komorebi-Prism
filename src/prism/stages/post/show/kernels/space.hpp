// SHOW's part of the command space (prism.core.fields, layout "show"): its address is
// the space's base (get_write_ptr) and the part's byte, a define of the build; the
// view's places in it, defines of the class's make.
#pragma once

#include <stdint.h>

namespace show_space {

    // The converted pages, the profile page, the buckets (show.h kShowScratchPages).
    constexpr uint32_t scratch(uint32_t base) {
        return base + PRISM_SPACE_SHOW_SCRATCH_AT;
    }

    // The view's slots (view.h kViewSlots pages), work (kViewWorkBytes) and words
    // (kViewRegionBytes), from the part's bytes the build defines.
    constexpr uint32_t view_slots(uint32_t base) {
        return scratch(base) + PRISM_SHOW_VIEW_SLOTS_AT;
    }

    constexpr uint32_t view_work(uint32_t base) {
        return scratch(base) + PRISM_SHOW_VIEW_WORK_AT;
    }

    constexpr uint32_t view_words(uint32_t base) {
        return scratch(base) + PRISM_SHOW_VIEW_WORDS_AT;
    }

}  // namespace show_space
