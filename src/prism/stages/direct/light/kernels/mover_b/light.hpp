// LIGHT on mover B: every item's colour planes back to the frame (a band: its rows),
// then the profile page to the core's page of the surface's profile tensor.
#pragma once

#include <stdint.h>

#include "../light.h"
#include "../../../../../core/include/surface.h"
#include "komorebi/device/tensors/km_ask.hpp"
#include "sends.hpp"

namespace light_k {

    // LIGHT of one command on mover B: `scratch` its directory page's buffer, `out`
    // the out pages'. False: gave up.
    template <typename Mover, typename Directory, typename Surface>
    bool write_command(
        const Mover& writer,
        const km_command_t& command,
        uint32_t scratch_buffer,
        uint32_t out,
        const Directory& directory_tensor,
        const Surface& surface_tensor
    ) {
        using fill_k::kDirFrame;
        using fill_k::kDirFrameMax;
        using fill_k::kDirIds;
        using fill_k::kDirItems;
        using fill_k::kDirMaxItems;
        using fill_k::kItemRow0Shift;
        using fill_k::kItemRow1Shift;
        using fill_k::kItemRowMask;
        using fill_k::kItemSlot;
        using fill_k::kOutPageBytes;
        using fill_k::kPlanes;
        using fill_k::kRowBytes;
        const uint32_t scratch = get_write_ptr(scratch_buffer);
        volatile tt_l1_ptr uint32_t* directory = km::l1(scratch);
        // the profile tensor from the surface's directory (surface.h
        // kSurfaceLightProfile)
        if (!km::read_pages(writer, command, surface_tensor, writer.me(), 1, scratch) ||
            !writer_read_done(writer, command.sequence)) {
            return false;
        }
        invalidate_l1_cache();
        const uint32_t profile_address = directory[kSurfaceLightProfile];
        if (!km::read_pages(
                writer, command, directory_tensor, writer.me(), 1, scratch
            ) ||
            !writer_read_done(writer, command.sequence)) {
            return false;
        }
        invalidate_l1_cache();
        const uint32_t items = directory[kDirItems],
                       tensor_pages = directory[kDirFrame];
        if (tensor_pages == 0 || tensor_pages % kPlanes != 0 || items > kDirMaxItems) {
            writer.gave_up(
                km::kStWriter, fill_k::kGaveBadItem, kWhereLightBad, 0, command.sequence
            );
            *writer.control(KM_CONTROL_STOP) = 1;
            return false;
        }
        for (uint32_t item = 0; item <= items; ++item) {
            if (!writer.wait_front(out, kLightOutPages)) {
                return true;
            }
            if (!item_fits(writer, out, kLightOutPages, command.sequence)) {
                return false;
            }
            if (item == items) {  // the profile item: the pack CPU's counters
                if (profile_address != 0) {
                    const InterleavedAddrGen<true> profiles = {
                        .bank_base_address = profile_address,
                        .page_size = kLightProfBytes
                    };
                    noc_async_write(
                        get_read_ptr(out),
                        get_noc_addr(writer.me(), profiles),
                        kLightProfBytes
                    );
                    if (!writes_sent(writer, command.sequence)) {
                        return false;
                    }
                }
                cb_pop_front(out, kLightOutPages);
                break;
            }
            const uint32_t id = directory[kDirIds + item];
            const uint32_t page = (id & kItemSlot) * kPlanes;
            if (page / tensor_pages >= kDirFrameMax) {
                writer.gave_up(
                    km::kStWriter,
                    fill_k::kGaveBadItem,
                    kWhereLightBad,
                    0,
                    command.sequence
                );
                *writer.control(KM_CONTROL_STOP) = 1;
                return false;
            }
            const uint32_t first_row = id >> kItemRow0Shift & kItemRowMask;
            const uint32_t end_row = id >> kItemRow1Shift & kItemRowMask;
            const uint32_t byte_offset = first_row * kRowBytes;
            const uint32_t bytes =
                (end_row > 0 ? (end_row - first_row) * kRowBytes : kOutPageBytes);
            const InterleavedAddrGen<true> frame_tensor = {
                .bank_base_address = directory[kDirFrame + 1 + page / tensor_pages],
                .page_size = kOutPageBytes
            };
            const uint32_t source = get_read_ptr(out) + byte_offset;
            for (
                uint32_t plane = kLightFirstPlane;
                plane < kLightFirstPlane + kLightColourPlanes;
                ++plane
            ) {
                noc_async_write(
                    source + plane * kOutPageBytes,
                    get_noc_addr(
                        (page + plane) % tensor_pages, frame_tensor, byte_offset
                    ),
                    bytes
                );
            }
            if (!writes_sent(writer, command.sequence)) {
                return false;
            }
            cb_pop_front(out, kLightOutPages);
        }
        return true;
    }

    // The handler's mover B: its buffers by the class's header, its words.
    template <typename Mover, typename Directory, typename Glass, typename Surface>
    inline bool light_writer(
        Mover& movement,
        const km_command_t& command,
        const Directory& directory,
        uint32_t table,
        uint32_t shade_table,
        uint32_t camera,
        const Glass& glass,
        const Surface& surface,
        uint32_t bank_grid,
        uint32_t mode
    ) {
        static_cast<void>(table);
        static_cast<void>(shade_table);
        static_cast<void>(camera);
        static_cast<void>(glass);
        static_cast<void>(bank_grid);
        static_cast<void>(mode);
        return write_command(
            movement, command, kFieldWriterPage, kFieldOutRing, directory, surface
        );
    }

}  // namespace light_k
