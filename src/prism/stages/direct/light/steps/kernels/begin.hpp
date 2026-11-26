// The light step on mover A, once a command before its first tile thread is handed
// on: the kept table page (LIGHT's table, the view's camera into it, and with a glass
// layer SHADE's table after it), as mover_a/table.hpp reads it for a command.
#pragma once

#include <stdint.h>

#include "../../../../../core/include/grid.h"
#include "../../../../../core/include/thread/frame.h"
#include "../../kernels/light.h"
#include "api/dataflow/dataflow_api.h"
#include "light_step.h"

namespace light_step {

    using namespace light_k;

    // The table page into the step's keep `light_table`. False: a word out of range or
    // a read gave up (recorded at the step's places).
    template <typename Ctx>
    bool light_begin(Ctx& ctx) {
        const volatile uint32_t* page = ctx.page;
        const uint32_t bank_plus_one = bank_word(page[TF_GRID]);
        const uint32_t table = page[PRISM_TF_LIGHT_TABLE];
        if (bank_plus_one == 0 || table == 0 || page[TF_CAMERA] == 0) {
            ctx.bad(kWhereLightStepBad);
            return false;
        }
        const uint32_t bank = bank_plus_one - 1;
        const uint32_t keep = ctx.light_table;
        auto arrived = [] {
            return ncrisc_noc_reads_flushed(noc_index);
        };
        noc_async_read(
            get_noc_addr_from_bank_id<true>(bank, table), keep, kLightTableBytes
        );
        if (!ctx.wait(arrived, kWhereLightStepTable)) {  // the camera after the table
            return false;
        }
        noc_async_read(
            get_noc_addr_from_bank_id<true>(bank, page[TF_CAMERA]),
            keep + 4 * kLtCamera,
            4 * kCamWordsShade
        );
        const uint32_t shade_table = page[PRISM_TF_LIGHT_SHADE_TABLE];
        if (shade_table != 0) {  // the glass form's materials: tau and weight
            noc_async_read(
                get_noc_addr(
                    0,
                    InterleavedAddrGen<true>{
                        .bank_base_address = shade_table, .page_size = kShadeTableBytes
                    }
                ),
                keep + 4 * kLightShadeTableAt,
                kLightShadeTableBytes
            );
        }
        return ctx.wait(arrived, kWhereLightStepCamera);
    }

}  // namespace light_step
