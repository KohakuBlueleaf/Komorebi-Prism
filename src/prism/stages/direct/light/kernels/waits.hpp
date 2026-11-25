// LIGHT's compute threads' waits: the timed waits and give-ups of the pack thread's
// mails, at LIGHT's places in the writer's gave-up word.
#pragma once

#include <stdint.h>

#include "../../../../core/include/compute_mail.hpp"
#include "light.h"
#include "from_raster.hpp"

namespace light_k {

    inline compute_mail::Waits waits_of(uint32_t control) {
        return {
            {control,
             fill_k::kGaveWait,
             fill_k::kGaveBadItem,
             kWhereLightMail,
             kWhereLightFront,
             kWhereLightBad},
            fill_k::kWaitCycles
        };
    }

}  // namespace light_k
