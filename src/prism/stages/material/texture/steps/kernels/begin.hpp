// The material step's begin on the data-movement CPU that takes a command first, once
// a command before its first thread: SHADE's table (the tensor of the step's word) into
// the common field frame_table; lit, the view's camera words into the step's keep.
#pragma once

#include <stdint.h>

#include "../../../../../core/include/grid.h"
#include "../../../../../core/include/texel_pages/ask.hpp"
#include "../../../../../core/include/thread/frame.h"
#include "../../../../raster/kernels/common/layouts.hpp"
#include "../../kernels/shade.h"

namespace material_step {

    // The table of page word `table_word` into frame_table and, when `camera_to` is not
    // 0, the camera's kCamWordsShade words (TF_CAMERA in the bank of TF_GRID) to L1
    // `camera_to`. False: a bad word or a read that gave up (recorded).
    inline bool read_begin(
        prism_frame::MoverContext& ctx, uint32_t table_word, uint32_t camera_to
    ) {
        const uint32_t table = ctx.page[table_word];
        const uint32_t grid = ctx.page[TF_GRID];
        if (table == 0 || (camera_to != 0 && bank_word(grid) == 0)) {
            return ctx.gave_up(km::kGaveBadItem, kWhereShadeBad);
        }
        const InterleavedAddrGen<true> tensor = {
            .bank_base_address = table, .page_size = kShadeTableBytes
        };
        noc_async_read(
            get_noc_addr(0, tensor), get_write_ptr(kFieldFrameTable), kShadeTableBytes
        );
        if (camera_to != 0) {
            const uint64_t camera = get_noc_addr_from_bank_id<true>(
                bank_word(grid) - 1, ctx.page[TF_CAMERA]
            );
            noc_async_read(camera, camera_to, 4 * kCamWordsShade);
        }
        if (!texel_pages::reads_arrived(ctx.movement)) {
            return ctx.gave_up(km::kGaveWait, kWhereShadeReader);
        }
        return true;
    }

}  // namespace material_step
