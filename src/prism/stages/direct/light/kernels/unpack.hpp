// LIGHT on the unpack CPU: the pack CPU's mails served (a buffer's front page, a pop)
// until its end.
#pragma once

#include <stdint.h>

#include "waits.hpp"

namespace light_k {

    // The handler's unpack CPU.
    inline void light_unpack(
        km::Compute& compute,
        const km_command_t& command,
        uint32_t table,
        uint32_t shade_table,
        uint32_t camera,
        uint32_t bank_grid,
        uint32_t mode
    ) {
        static_cast<void>(command);
        static_cast<void>(table);
        static_cast<void>(shade_table);
        static_cast<void>(camera);
        static_cast<void>(bank_grid);
        static_cast<void>(mode);
        compute_mail::serve_mails(waits_of(compute.control()));
    }

}  // namespace light_k
