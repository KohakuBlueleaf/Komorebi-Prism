// SHADE's compute threads' waits: the timed waits and give-ups of the texel pages'
// mails, at SHADE's places in the writer's gave-up word.
#pragma once

#include <stdint.h>

#include "../../../../core/include/compute_mail.hpp"
#include "../../../raster/kernels/common/layouts.hpp"
#include "shade.h"

namespace shade_k {

    inline compute_mail::Waits waits_of(uint32_t control) {
        return {
            {control,
             fill_k::kGaveWait,
             fill_k::kGaveBadItem,
             kWhereShadeMail,
             kWhereShadeFront,
             kWhereShadeBad},
            fill_k::kWaitCycles
        };
    }

}  // namespace shade_k
