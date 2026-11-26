// The movers' waits of the geometry thread and the sums, each limited by the run's wait
// limit and given up with a `where` of its own (geometry.h kWhere*).
#pragma once

#if !defined(COMPILE_FOR_TRISC)

#include <stdint.h>

#include "api/dataflow/dataflow_api.h"
#include "komorebi/device/km_worker.hpp"

namespace geometry_k {

    // Room for `pages` pages at the back of `cb`, then reserved. False: gave up.
    template <typename Core>
    inline bool room(const Core& core, uint32_t cb, uint32_t pages, uint32_t where) {
        if (!core.wait(
                [&] {
                    return cb_pages_reservable_at_back(cb, pages);
                },
                where
            )) {
            return false;
        }
        cb_reserve_back(cb, pages);
        return true;
    }

    // `pages` pages at the front of `cb`, then waited for. False: gave up.
    template <typename Core>
    inline bool front(const Core& core, uint32_t cb, uint32_t pages, uint32_t where) {
        if (!core.wait(
                [&] {
                    return cb_pages_available_at_front(cb, pages);
                },
                where
            )) {
            return false;
        }
        cb_wait_front(cb, pages);
        return true;
    }

    // This mover's writes acknowledged. False: gave up.
    template <typename Core>
    inline bool sent(const Core& core, uint32_t where) {
        return core.wait(
            [] {
                return ncrisc_noc_nonposted_writes_flushed(noc_index);
            },
            where
        );
    }

    // This mover's reads landed. False: gave up.
    template <typename Core>
    inline bool landed(const Core& core, uint32_t where) {
        return core.wait(
            [] {
                return ncrisc_noc_reads_flushed(noc_index);
            },
            where
        );
    }

    // A DRAM address: byte `offset` of page `page` (of `bytes`) of an interleaved
    // tensor at `base` (bank 0), or of bank (bank - 1) from `base` (pages contiguous).
    inline uint64_t dram(
        uint32_t bank, uint32_t base, uint32_t page, uint32_t bytes, uint32_t offset = 0
    ) {
        if (bank != 0) {
            return get_noc_addr_from_bank_id<true>(
                bank - 1, base + page * bytes + offset
            );
        }
        const InterleavedAddrGen<true> tensor = {
            .bank_base_address = base, .page_size = bytes
        };
        return tensor.get_noc_addr(page, offset);
    }

}  // namespace geometry_k

#endif
