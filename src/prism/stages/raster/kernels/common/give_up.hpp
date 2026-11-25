// A give-up into the writer's gave-up word (the first one is kept) and the stop word,
// from any of a core's CPUs; `control` is its control block's address.
#pragma once

#include <stdint.h>

#include "komorebi/device/km_worker.hpp"

namespace setup_k {

    inline void give_up(uint32_t control, uint32_t code, uint32_t where) {
        volatile uint32_t* state = (reinterpret_cast<volatile uint32_t*>(
            control + KM_CONTROL_STATE
        ));
        if (state[km::kStWriter] == 0) {
            state[km::kStWriter] = code | where << 8;
        }
        *reinterpret_cast<volatile uint32_t*>(control + KM_CONTROL_STOP) = 1;
    }

}  // namespace setup_k
