// SHOW's profile on mover B: the writer's cycles and counts in a scratch page, sent to
// this core's page of the profile tensor.
#pragma once

#include <stdint.h>

#include "api/dataflow/dataflow_api.h"
#include "komorebi/device/km_worker.hpp"
#include "write.hpp"

namespace show_k {

    // The last writes sent, then the profile page to page me() of the profile tensor
    // at `profile_address`; false: gave up (recorded).
    template <typename Writer_>
    bool send_profile(
        const Writer_& writer,
        const km_command_t& command,
        const Writer& show,
        uint32_t profile_address
    ) {
        if (!show.sent(writer, command)) {
            return false;
        }
        const uint32_t page = show.scratch + kShowProfPage * kShowPageBytes;
        volatile tt_l1_ptr uint32_t* profile = km::l1(page);
        for (uint32_t word = 0; word < kShowProfBytes / 4; ++word) {
            profile[word] = 0;
        }
        profile[kShowProfConvert] = show.convert;
        profile[kShowProfWait] = show.wait;
        profile[kShowProfWrite] = show.write;
        profile[kShowProfTotal] = km::wall() - show.started;
        profile[kShowProfItems] = show.items;
        profile[kShowProfRows] = show.rows;
        const InterleavedAddrGen<true> profiles = {
            .bank_base_address = profile_address, .page_size = kShowProfBytes
        };
        noc_async_write(page, get_noc_addr(writer.me(), profiles, 0), kShowProfBytes);
        return show.sent(writer, command);
    }

}  // namespace show_k
