// LIGHT on mover A: the directory pages it reads first (the surface's, the glass
// layer's, the opaque one's) and the words it keeps of them.
#pragma once

#include <stdint.h>

#include "../../../../../core/include/surface.h"
#include "../from_raster.hpp"
#include "../light.h"
#include "api/dataflow/dataflow_api.h"
#include "komorebi/device/km_worker.hpp"
#include "komorebi/device/tensors/km_ask.hpp"

namespace light_k {

    using fill_k::kDirFrame;
    using fill_k::kDirFrameMax;
    using fill_k::kDirItems;
    using fill_k::kDirMaxItems;
    using fill_k::kPlanes;

    // Timed noc_async_read_barrier. False: gave up (recorded in the reader's word).
    template <typename Reader>
    bool read_done(const Reader& reader, uint32_t sequence) {
        const uint32_t code = reader.poll(
            [] {
                return ncrisc_noc_reads_flushed(noc_index);
            },
            reader.args().wait_limit
        );
        if (code == km::kGaveNone) {
            return true;
        }
        reader.gave_up(km::kStReader, code, fill_k::kWhereReadDone, 0, sequence);
        return false;
    }

    // The surface directory's words: both frames', LIGHT's table, profile, pages.
    struct SurfaceWords {
        uint32_t words[kSurfaceWords + 3] = {};

        const uint32_t* first() const {
            return words;
        }

        const uint32_t* second() const {
            return words + kDirFrameMax + 1;
        }

        uint32_t table() const {
            return words[kSurfaceWords];
        }

        uint32_t pages() const {
            return words[kSurfaceWords + 2];
        }
    };

    // Page `me` of a directory tensor into `scratch`, the L1 cache invalidated. False:
    // gave up.
    template <typename Mover, typename Directory>
    bool read_directory(
        const Mover& reader,
        const km_command_t& command,
        const Directory& directory,
        uint32_t scratch
    ) {
        if (!km::read_pages(reader, command, directory, reader.me(), 1, scratch) ||
            !read_done(reader, command.sequence)) {
            return false;
        }
        invalidate_l1_cache();
        return true;
    }

    // The surface directory's words into `surface`; false: gave up or not two frames
    // of five planes.
    template <typename Mover, typename Surface>
    inline bool surface_words(
        const Mover& reader,
        const km_command_t& command,
        const Surface& directory,
        uint32_t scratch,
        SurfaceWords& surface
    ) {
        if (!read_directory(reader, command, directory, scratch)) {
            return false;
        }
        volatile tt_l1_ptr uint32_t* words = km::l1(scratch);
        for (uint32_t i = 0; i <= kDirFrameMax; ++i) {
            surface.words[i] = words[kDirFrame + i];
            surface.words[kDirFrameMax + 1 + i] = words[kSurfaceSecond + i];
        }
        surface.words[kSurfaceWords] = words[kSurfaceLightTable];
        surface.words[kSurfaceWords + 1] = words[kSurfaceLightProfile];
        surface.words[kSurfaceWords + 2] = words[kSurfaceLightPages];
        for (uint32_t frame = 0; frame < 2; ++frame) {
            const uint32_t tensor_pages = surface.words[(kDirFrameMax + 1) * frame];
            if (tensor_pages == 0 || tensor_pages % kPlanes != 0) {
                return false;
            }
        }
        return true;
    }

    // The glass layer's frame words (its directory's kDirFrame on); false: gave up or
    // not a frame of five planes.
    template <typename Mover, typename Directory>
    inline bool glass_words(
        const Mover& reader,
        const km_command_t& command,
        const Directory& directory,
        uint32_t scratch,
        uint32_t* frame
    ) {
        if (!read_directory(reader, command, directory, scratch)) {
            return false;
        }
        volatile tt_l1_ptr uint32_t* words = km::l1(scratch);
        for (uint32_t i = 0; i <= kDirFrameMax; ++i) {
            frame[i] = words[kDirFrame + i];
        }
        return frame[0] != 0 && frame[0] % kPlanes == 0;
    }

    // The opaque directory's page: its items and frame are sound.
    inline bool items_sound(volatile tt_l1_ptr uint32_t* directory) {
        const uint32_t items = directory[kDirItems];
        const uint32_t tensor_pages = directory[kDirFrame];
        return tensor_pages != 0 && tensor_pages % kPlanes == 0 &&
            items <= kDirMaxItems;
    }

}  // namespace light_k
