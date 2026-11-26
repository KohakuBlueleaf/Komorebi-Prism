// The material step's page requests on the pack CPU, through the loop's request
// rings: a pass of rows' pages (texel_pages::Pages, its ask list in the step's L1)
// asked in asks of at most FA_ENTRIES pages, the halves in turn, each into its slot of
// the step's page cache; all waited for, then the pass's rows gathered (the page_passes
// of texel_pages/passes.hpp on the loop's rings).
#pragma once

#include <stdint.h>

#include "../../../../../core/include/texel_pages/passes.hpp"
#include "../../../../../program/frame/kernels/pack.hpp"

namespace material_step {

    // Where a pass's pages come from and go: the loop's context, the textures' tensor,
    // the page cache (kShadeSlots pages, then the white one), the pass's ask list.
    struct Requests {
        prism_frame::ComputeContext* ctx = nullptr;
        uint32_t base = 0;
        uint32_t cache = 0;
        uint32_t* asked = nullptr;  // Pages' ask: page i at word 1 + i
    };

    // Pages `asked[1 .. count]` into cache slots 0 to count - 1, in asks of FA_ENTRIES
    // posted to the halves in turn, then every ask waited for. False: gave up.
    inline bool ask_pages(const Requests& requests, uint32_t count) {
        constexpr uint32_t kAsksMost = (kShadeSlots + FA_ENTRIES - 1) / FA_ENTRIES;
        uint32_t halves[kAsksMost];
        uint32_t posted = 0;
        for (uint32_t at = 0; at < count; at += FA_ENTRIES) {
            const uint32_t entries = count - at < FA_ENTRIES ? count - at : FA_ENTRIES;
            const uint32_t ask = prism_frame::ask_begin(
                *requests.ctx, requests.base, kTexPageBytes
            );
            if (ask == 0) {
                return false;
            }
            for (uint32_t i = 0; i < entries; ++i) {
                prism_frame::ask_entry(
                    ask,
                    i,
                    requests.asked[1 + at + i],
                    requests.cache + (at + i) * kTexPageBytes
                );
            }
            halves[posted++] = prism_frame::ask_post(*requests.ctx, ask, entries);
        }
        for (uint32_t i = 0; i < posted; ++i) {
            if (!prism_frame::ask_wait(*requests.ctx, halves[i])) {
                return false;
            }
        }
        return true;
    }

    // Rows [first, end) in passes whose pages fit the cache: scan(row) (false: full, it
    // starts the next pass), the pass's pages asked, gather(a, b). False: gave up.
    template <typename Scan, typename Gather>
    inline bool request_passes(
        const compute_mail::Waits& waits,
        const Requests& requests,
        uint32_t first,
        uint32_t end,
        texel_pages::Pages& pages,
        texel_pages::PassCounts& counts,
        Scan&& scan,
        Gather&& gather
    ) {
        uint32_t row = first;
        while (row < end) {
            const uint32_t started = km::wall();
            pages.ask = requests.asked;
            pages.clear();
            const uint32_t pass_first = row;
            while (row < end && scan(row)) {
                ++row;
            }
            if (row == pass_first) {  // one row cannot need more pages than slots
                compute_mail::stop(
                    waits.stops, waits.stops.gave_bad, waits.stops.where_bad
                );
                return false;
            }
            const uint32_t now = km::wall();
            counts.scan += now - started;
            if (pages.count != 0) {
                if (!ask_pages(requests, pages.count)) {
                    return false;
                }
                counts.pages += pages.count;
            }
            counts.wait += km::wall() - now;
            counts.passes++;
            if (!gather(pass_first, row)) {
                return false;
            }
        }
        return true;
    }

}  // namespace material_step
