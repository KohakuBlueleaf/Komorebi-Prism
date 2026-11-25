// The passes' profile: each CPU's words in the core's L1 profile page (setup.h kSProf),
// the writer's added and the page's 128 bytes of a handler sent to its tensor page.
#pragma once

#include <stdint.h>

#include "komorebi/device/km_worker.hpp"
#include "layouts.hpp"
#include "noc.hpp"

namespace setup_k {

    // A command's start on a CPU, for its profile words.
    struct Started {
        uint32_t at = km::wall();
    };

    // The writer's profile counters for one command (cycles, bytes, pages).
    struct WriterProfile {
        uint32_t wait = 0, write = 0, bytes = 0, pages = 0;
    };

    // The writer's words at kSProfWriter, then the page's 128 bytes to byte 128 x
    // (handler - kHandlerCount) of this core's page at `profile_address` (0: none).
    template <typename Writer>
    bool send_profile(
        const Writer& writer,
        uint32_t page,
        uint32_t profile_address,
        uint32_t handler,
        const WriterProfile& profile,
        uint32_t started
    ) {
        if (profile_address == 0) {
            return true;
        }
        invalidate_l1_cache();
        volatile tt_l1_ptr uint32_t* words = km::l1(page);
        words[kSProfWriter + 0] = profile.wait;
        words[kSProfWriter + 1] = profile.write;
        words[kSProfWriter + 2] = km::wall() - started;
        words[kSProfWriter + 3] = profile.bytes;
        words[kSProfWriter + 4] = started;
        words[kSProfWriter + 5] = profile.pages;
        noc_async_write(
            page,
            noc_address(
                0,
                profile_address,
                writer.me(),
                kSProfPageBytes,
                128 * (handler - kHandlerCount)
            ),
            128
        );
        return flushed(writer);
    }

}  // namespace setup_k
