// The raster's parts of the command space (prism.core.fields, layout "raster"): a
// part's address is the space's base (get_write_ptr) and the part's byte, a define of
// the build.
#pragma once

#include <stdint.h>

namespace raster_space {

    // COUNT's counters: entries, then rows at kTiles.
    constexpr uint32_t counters(uint32_t base) {
        return base + PRISM_SPACE_RASTER_COUNTERS_AT;
    }

    // COUNT's histograms, kept for HIST; SETUP's prefixes.
    constexpr uint32_t kept_hist(uint32_t base) {
        return base + PRISM_SPACE_KEPT_HIST_AT;
    }

}  // namespace raster_space
