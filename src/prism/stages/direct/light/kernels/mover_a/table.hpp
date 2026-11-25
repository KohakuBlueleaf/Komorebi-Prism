// LIGHT on mover A: the table page for compute: LIGHT's table, the camera into it, and
// in the glass form SHADE's table after it.
#pragma once

#include <stdint.h>

#include "../../../../../core/include/grid.h"
#include "../light.h"
#include "../../../../../core/include/surface.h"
#include "api/dataflow/dataflow_api.h"
#include "directories.hpp"

namespace light_k {

    // Where the table page's parts come from: the table's address in the bank of
    // `bank_grid` (0: the surface's table tensor), the camera's there, SHADE's table.
    struct TableWords {
        uint32_t table;
        uint32_t camera;
        uint32_t bank_grid;
        uint32_t shade_table;  // its tensor's address
        bool glass;            // the glass form: SHADE's table read
    };

    // The table page reserved, read and pushed to compute. False: gave up.
    template <typename Mover>
    bool read_table(
        const Mover& reader,
        const km_command_t& command,
        const TableWords& words,
        const SurfaceWords& surface,
        uint32_t buffer
    ) {
        if (!reader.reserve(buffer, 1)) {
            return false;
        }
        const uint32_t bank = bank_word(words.bank_grid) - 1;
        const uint32_t page = get_write_ptr(buffer);
        const uint64_t table_source = words.table != 0
            ? get_noc_addr_from_bank_id<true>(bank, words.table)
            : get_noc_addr(
                  0,
                  InterleavedAddrGen<true>{
                      .bank_base_address = surface.table(),
                      .page_size = kLightTableBytes
                  }
              );
        noc_async_read(table_source, page, kLightTableBytes);
        noc_async_read_barrier();  // the camera after the table's words
        noc_async_read(
            get_noc_addr_from_bank_id<true>(bank, words.camera),
            page + 4 * kLtCamera,
            4 * kCamWordsShade
        );
        if (words
                .glass) {  // SHADE's table after LIGHT's: the materials' tau and weight
            noc_async_read(
                get_noc_addr(
                    0,
                    InterleavedAddrGen<true>{
                        .bank_base_address = words.shade_table,
                        .page_size = kShadeTableBytes
                    }
                ),
                page + 4 * kLightShadeTableAt,
                kLightShadeTableBytes
            );
        }
        if (!read_done(reader, command.sequence)) {
            return false;
        }
        cb_push_back(buffer, 1);
        return true;
    }

}  // namespace light_k
