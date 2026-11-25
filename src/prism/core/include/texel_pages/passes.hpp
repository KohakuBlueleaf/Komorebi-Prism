// The pack thread's passes of rows (SHADE, LIGHT): each pass's pages asked of mover A,
// waited for, then its rows gathered; the cycles and pages counted.
#pragma once

#include <stdint.h>

#include "../compute_mail.hpp"
#include "pages.hpp"

namespace texel_pages {

    using compute_mail::Waits;

#ifdef TRISC_PACK
    // A command's page passes: cycles finding pages, waiting for them; passes, pages.
    struct PassCounts {
        uint32_t scan = 0, wait = 0, passes = 0, pages = 0;
    };

    // Rows [first, end) in passes whose pages fit the slots: scan(row) (false: full,
    // it starts the next pass), mover A reads them (the `ask` and `done` buffers),
    // gather(a, b).
    template <typename Scan, typename Gather>
    inline bool page_passes(
        const Waits& waits,
        uint32_t ask,
        uint32_t done,
        uint32_t first,
        uint32_t end,
        Pages& pages,
        PassCounts& counts,
        Scan&& scan,
        Gather&& gather
    ) {
        uint32_t row = first;
        while (row < end) {
            const uint32_t started = km::wall();
            if (!compute_mail::reserve(waits, ask, 1)) {
                return false;
            }
            pages.ask = reinterpret_cast<uint32_t*>(compute_mail::write_ptr(ask));
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
                pages.ask[0] = pages.count;
                compute_mail::push(ask, reinterpret_cast<uint32_t>(pages.ask), 1);
                if (compute_mail::front(waits, done, 1) == 0 ||
                    !compute_mail::pop(waits, done, 1)) {
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

    // The pack thread's last ask: the end of mover A's service.
    inline void ask_end(const Waits& waits, uint32_t ask) {
        if (compute_mail::reserve(waits, ask, 1)) {
            const uint32_t page = compute_mail::write_ptr(ask);
            *reinterpret_cast<volatile uint32_t*>(page) = kShadeAskEnd;
            compute_mail::push(ask, page, 1);
        }
    }
#endif

}  // namespace texel_pages
