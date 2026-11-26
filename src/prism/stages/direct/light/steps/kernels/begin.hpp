// The light step on the data-movement CPU that takes a command first, before its first
// thread: the kept table page (LIGHT's table from the regions' bank, the view's camera
// into it, as mover_a/table.hpp reads it for a command), then the field's version the
// frame's thread gave (its first page, units and scale), when it gave one.
#pragma once

#include <stdint.h>

#include "../../../../../core/include/thread/frame.h"
#include "../../kernels/light.h"
#include "api/dataflow/dataflow_api.h"
#include "komorebi/device/km_worker.hpp"
#include "light_step.h"

// The table page into the keep `table`. False: a word out of range or a read gave up
// (recorded at the step's places).
template <typename Ctx>
bool light_begin(Ctx& ctx) {
    using namespace light_k;
    using namespace light_step;
    const volatile tt_l1_ptr uint32_t* page = ctx.page;
    const uint32_t table = page[PRISM_TF_LIGHT_TABLE];
    if (table == 0 || page[TF_CAMERA] == 0) {
        return ctx.gave_up(km::kGaveBadItem, kWhereLightStepBad);
    }
    const uint32_t keep = ctx.kept(prism_frame::kKeptLightTable);
    auto arrived = [] {
        return ncrisc_noc_reads_flushed(noc_index);
    };
    noc_async_read(
        get_noc_addr_from_bank_id<true>(ctx.bank, table), keep, kLightTableBytes
    );
    if (!ctx.movement.wait(arrived, kWhereLightStepTable)) {  // the camera after it
        return false;
    }
    noc_async_read(
        get_noc_addr_from_bank_id<true>(ctx.bank, page[TF_CAMERA]),
        keep + 4 * kLtCamera,
        4 * kCamWordsShade
    );
    if (!ctx.movement.wait(arrived, kWhereLightStepCamera)) {
        return false;
    }
    if (page[PRISM_TF_LIGHT_FIELD_FIRST] != 0) {  // the field's version of the frame
        volatile tt_l1_ptr uint32_t* words = km::l1(keep);
        words[kLtFieldFirst] = page[PRISM_TF_LIGHT_FIELD_FIRST];
        for (uint32_t channel = 0; channel < 3; ++channel) {
            words[kLtFieldUnit + channel] = page[PRISM_TF_LIGHT_FIELD_UNIT_R + channel];
        }
        words[kLtFieldScale] = page[PRISM_TF_LIGHT_FIELD_SCALE];
    }
    return true;
}
