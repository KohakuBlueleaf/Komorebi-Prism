// The passes' DRAM addresses on a mover: an interleaved tensor's page, or a page of an
// X280 thread's region in one bank; the movers' timed waits for their NoC traffic.
#pragma once

#include <stdint.h>

#include "api/dataflow/dataflow_api.h"
#include "komorebi/device/km_worker.hpp"

namespace setup_k {

    // Byte `offset` of page `page` (of `bytes`) at `base`: with bank 0 an interleaved
    // tensor's page, otherwise bank (bank - 1)'s address base + page x bytes + offset.
    inline uint64_t noc_address(
        uint32_t bank, uint32_t base, uint32_t page, uint32_t bytes, uint32_t offset = 0
    ) {
        if (bank != 0) {
            return (
                get_noc_addr_from_bank_id<true>(bank - 1, base + page * bytes + offset)
            );
        }
        const InterleavedAddrGen<true> tensor = {
            .bank_base_address = base, .page_size = bytes
        };
        return get_noc_addr(page, tensor, offset);
    }

    // A region's bank word as the passes take it: 1 + its DRAM bank.
    template <typename Region>
    uint32_t bank_of(const Region& region) {
        return region.bank + 1;
    }

    // The mover's writes flushed, within the run's wait limit.
    template <typename Mover>
    bool flushed(const Mover& mover) {
        return mover.poll(
                   [] {
                       return ncrisc_noc_nonposted_writes_flushed(noc_index);
                   },
                   mover.args().wait_limit
               ) == km::kGaveNone;
    }

    // The mover's reads arrived, within the run's wait limit.
    template <typename Mover>
    bool arrived(const Mover& mover) {
        return mover.poll(
                   [] {
                       return ncrisc_noc_reads_flushed(noc_index);
                   },
                   mover.args().wait_limit
               ) == km::kGaveNone;
    }

}  // namespace setup_k
