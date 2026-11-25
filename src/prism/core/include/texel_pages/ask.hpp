// Mover A's side of the texel pages (SHADE, LIGHT): an ask of the pack thread served,
// its pages read into the slots and a done page pushed.
#pragma once

#include <stdint.h>

#include "api/dataflow/dataflow_api.h"
#include "komorebi/device/km_worker.hpp"
#include "protocol.h"

namespace texel_pages {

    // The ask and done buffers and the slots' L1 address.
    struct AskBuffers {
        uint32_t ask;
        uint32_t done;
        uint32_t slots;
    };

    // A step of the pack thread's asks: none, waiting for room to answer, served
    // (pages into the slots, answered), the pack thread's end, failed.
    enum AskStep : uint32_t { kAskNone, kAskBlocked, kAskServed, kAskEnd, kAskFailed };

    // The mover's reads arrived, within the run's wait limit.
    template <typename Mover>
    bool reads_arrived(const Mover& mover) {
        return mover.poll(
                   [] {
                       return ncrisc_noc_reads_flushed(noc_index);
                   },
                   mover.args().wait_limit
               ) == km::kGaveNone;
    }

    template <typename Mover>
    AskStep serve_ask(
        const Mover& mover,
        const AskBuffers& buffers,
        const InterleavedAddrGen<true>& pages
    ) {
        if (!cb_pages_available_at_front(buffers.ask, 1)) {
            return kAskNone;
        }
        invalidate_l1_cache();
        volatile tt_l1_ptr uint32_t* ask = km::l1(get_read_ptr(buffers.ask));
        const uint32_t count = ask[0];
        if (count == kShadeAskEnd) {
            cb_pop_front(buffers.ask, 1);
            return kAskEnd;
        }
        if (count > kShadeSlots) {
            return kAskFailed;
        }
        if (!cb_pages_reservable_at_back(buffers.done, 1)) {
            return kAskBlocked;
        }
        for (uint32_t slot = 0; slot < count; ++slot) {
            noc_async_read(
                get_noc_addr(ask[1 + slot], pages),
                buffers.slots + slot * kTexPageBytes,
                kTexPageBytes
            );
        }
        if (!reads_arrived(mover)) {
            return kAskFailed;
        }
        cb_pop_front(buffers.ask, 1);
        cb_reserve_back(buffers.done, 1);
        cb_push_back(buffers.done, 1);
        return kAskServed;
    }

}  // namespace texel_pages
