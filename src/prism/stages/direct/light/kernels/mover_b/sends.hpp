// LIGHT on mover B: its timed waits for reads and writes, and the out item's fit in
// its buffer (a give-up recorded in the writer's word, the stop set).
#pragma once

#include <stdint.h>

#include "../from_raster.hpp"
#include "api/dataflow/dataflow_api.h"
#include "komorebi/device/km_worker.hpp"

namespace light_k {

    // An item of `pages` pages at the read pointer of `out` must end inside it.
    template <typename Writer>
    bool item_fits(
        const Writer& writer, uint32_t out, uint32_t pages, uint32_t sequence
    ) {
        if (get_read_ptr(out) + pages * fill_k::kOutPageBytes <=
            get_local_cb_interface(out).fifo_limit) {
            return true;
        }
        writer.gave_up(
            km::kStWriter, fill_k::kGaveBadItem, fill_k::kWhereBadSend, 0, sequence
        );
        *writer.control(KM_CONTROL_STOP) = 1;
        return false;
    }

    // Timed NoC waits: reads arrived, or writes sent. False: gave up (recorded).
    template <typename Writer, typename Ready>
    bool noc_done(
        const Writer& writer, Ready ready, uint32_t where, uint32_t sequence
    ) {
        const uint32_t code = writer.poll(ready, writer.args().wait_limit);
        if (code == km::kGaveNone) {
            return true;
        }
        writer.gave_up(km::kStWriter, code, where, 0, sequence);
        return false;
    }

    template <typename Writer>
    bool writer_read_done(const Writer& writer, uint32_t sequence) {
        return noc_done(
            writer,
            [] {
                return ncrisc_noc_reads_flushed(noc_index);
            },
            fill_k::kWhereReadDone,
            sequence
        );
    }

    template <typename Writer>
    bool writes_sent(const Writer& writer, uint32_t sequence) {
        return noc_done(
            writer,
            [] {
                return ncrisc_noc_nonposted_writes_sent(noc_index);
            },
            fill_k::kWhereFlush,
            sequence
        );
    }

}  // namespace light_k
