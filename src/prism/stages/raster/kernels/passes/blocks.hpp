// COUNT and SETUP on mover A: the reader's profile words after the lines have read the
// camera's page and the core's mesh blocks.
#pragma once

#include <stdint.h>

#include "../common/layouts.hpp"
#include "komorebi/device/km_worker.hpp"

namespace setup_k {

    // The reader's words at kSProfReader of the L1 profile page: the blocks' wait and
    // read cycles (the mesh line's), the whole time since `started`, the bytes (the
    // camera's numbers and kMeshBytes a block), the start.
    inline void reader_profile(
        uint32_t profile_buffer, uint32_t cycles, uint32_t blocks, uint32_t started
    ) {
        volatile tt_l1_ptr uint32_t* profile = km::l1(get_write_ptr(profile_buffer));
        profile[kSProfReader + 0] = 0;
        profile[kSProfReader + 1] = cycles;
        profile[kSProfReader + 2] = km::wall() - started;
        profile[kSProfReader + 3] = 4 * kCamWords + blocks * kMeshBytes;
        profile[kSProfReader + 4] = started;
    }

}  // namespace setup_k
