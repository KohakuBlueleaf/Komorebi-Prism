// SHADE on the unpack thread: it serves the pack thread's mails (the buffers' fronts
// and pops) until the pack thread's end.
#pragma once

#include <stdint.h>

#include "waits.hpp"

namespace shade_k {

    inline void shade_unpack(
        km::Compute& compute,
        const km_command_t& command,
        uint32_t opaque,
        uint32_t mode,
        uint32_t grid,
        uint32_t camera
    ) {
        static_cast<void>(command);
        static_cast<void>(opaque);
        static_cast<void>(mode);
        static_cast<void>(grid);
        static_cast<void>(camera);
        compute_mail::serve_mails(waits_of(compute.control()));
    }

}  // namespace shade_k
