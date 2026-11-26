// The material step's counters on the pack CPU (shade.h kShadeProf*) and a tile's page
// passes added: pack/profile.hpp's, without its profile item (no out ring here).
#pragma once

#include <stdint.h>

#include "../../../../../core/include/texel_pages/passes.hpp"
#include "../../kernels/pack/vector.hpp"

namespace shade_k {

    struct Counters {
        uint32_t values[kShadeProfWords] = {};
    };

    // The page passes' counts into the counters.
    inline void add_counts(Counters& counters, const texel_pages::PassCounts& counts) {
        counters.values[kShadeProfScan] += counts.scan;
        counters.values[kShadeProfWaitPages] += counts.wait;
        counters.values[kShadeProfPasses] += counts.passes;
        counters.values[kShadeProfPages] += counts.pages;
        if (counts.pages > counters.values[kShadeProfItemPages]) {
            counters.values[kShadeProfItemPages] = counts.pages;
        }
        counters.values[kShadeProfItemPasses] += counts.passes > 1 ? 1 : 0;
    }

}  // namespace shade_k
