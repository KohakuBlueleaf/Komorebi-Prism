// The sums' handler on both movers (sums.py, km.kernel entry geometry_k::sums): each
// mover its turns of this core's slices, in its own scratch field.
#pragma once

#include <stdint.h>

#include "sums/sums.hpp"

namespace geometry_k {

    static_assert(
        sizeof(SumScratch) <= kFieldScratchAPages * kFieldScratchAPageBytes &&
            sizeof(SumScratch) <= kFieldScratchBPages * kFieldScratchBPageBytes,
        "the sums' scratch fields hold a SumScratch (sums.py SCRATCH_WORDS)"
    );

    // SUMS on each mover. False: gave up (recorded).
    inline bool sums_movement(km::Movement& movement, const km_command_t& command) {
        constexpr uint32_t scratch = km::kMover == km::kMoverA ? kFieldScratchA
                                                               : kFieldScratchB;
        return sums_run(movement, command, get_write_ptr(scratch));
    }

}  // namespace geometry_k
