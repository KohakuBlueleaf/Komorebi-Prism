// SHADE's profile on the pack thread: its counters (shade.h kShadeProf*), a command's
// page passes added, and the profile item pushed to mover B after the last item.
#pragma once

#include <stdint.h>

#include "../../../../../core/include/texel_pages/passes.hpp"
#include "vector.hpp"

namespace shade_k {

    struct Counters {
        uint32_t values[kShadeProfWords] = {};
    };

    // SHADE's pass counts into its profile.
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

    // The profile item: the counters, the command's cycles since `started`, in the
    // first words of kShadeOutPages pages of the out buffer.
    inline void profile_out(
        const compute_mail::Waits& waits, Counters& counters, uint32_t started
    ) {
        if (!compute_mail::reserve(waits, kFieldOutRing, kShadeOutPages)) {
            return;
        }
        counters.values[kShadeProfTotal] = km::wall() - started;
        volatile uint32_t* profile = reinterpret_cast<volatile uint32_t*>(
            compute_mail::write_ptr(kFieldOutRing)
        );
        for (uint32_t i = 0; i < kShadeProfBytes / 4; ++i) {
            profile[i] = i < kShadeProfWords ? counters.values[i] : 0;
        }
        compute_mail::push(
            kFieldOutRing,
            reinterpret_cast<uint32_t>(profile) + kShadeProfBytes - 4,
            kShadeOutPages
        );
    }

}  // namespace shade_k
