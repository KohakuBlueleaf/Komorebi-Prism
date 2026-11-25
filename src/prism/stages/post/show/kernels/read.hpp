// SHOW's and COPY's item read on mover A: an item's planes of the frame (a band: its
// rows' bytes) into the planes buffer, three pages an item.
#pragma once

#include <stdint.h>

#include "../../../raster/kernels/common/layouts.hpp"
#include "api/dataflow/dataflow_api.h"
#include "komorebi/device/km_worker.hpp"

namespace show_k {
#include "show.h"

    using fill_k::kDirFrameMax;
    using fill_k::kItemRow0Shift;
    using fill_k::kItemRow1Shift;
    using fill_k::kItemRowMask;
    using fill_k::kItemSlot;
    using fill_k::kOutPageBytes;
    using fill_k::kPlanes;
    using fill_k::kRowBytes;
    using fill_k::kWhereReadDone;

    // Mover A's state for one command: the planes buffer, the frame's tensors from
    // the directory.
    struct Reader {
        uint32_t planes = 0;
        uint32_t tensor_pages = 0;  // pages a frame tensor
        uint32_t bases[kDirFrameMax] = {};

        // The directory's frame words (pages a tensor, then each one's address);
        // false: not a frame (the writer gives up for it).
        template <typename... Words>
        bool frame(uint32_t buffer, Words... words) {
            static_assert(sizeof...(Words) == 1 + kDirFrameMax);
            const uint32_t frames[] = {static_cast<uint32_t>(words)...};
            planes = buffer;
            tensor_pages = frames[0];
            for (uint32_t i = 0; i < kDirFrameMax; ++i) {
                bases[i] = frames[1 + i];
            }
            return tensor_pages != 0 && tensor_pages % kPlanes == 0;
        }

        // The reads arrived within the run's wait limit (false: gave up, recorded).
        template <typename Reader_>
        bool arrived(const Reader_& reader, const km_command_t& command) const {
            const uint32_t code = reader.poll(
                [] {
                    return ncrisc_noc_reads_flushed(noc_index);
                },
                reader.args().wait_limit
            );
            if (code == km::kGaveNone) {
                return true;
            }
            reader.gave_up(km::kStReader, code, kWhereReadDone, 0, command.sequence);
            return false;
        }

        // Planes [first, first + count) of item `id` into a reserved item of the
        // buffer, pushed; false: the command ends here.
        template <typename Reader_>
        bool item(
            const Reader_& reader,
            const km_command_t& command,
            uint32_t id,
            uint32_t first,
            uint32_t count
        ) const {
            const uint32_t page = (id & kItemSlot) * kPlanes;
            if (page / tensor_pages >= kDirFrameMax) {
                return false;
            }
            const uint32_t first_row = id >> kItemRow0Shift & kItemRowMask;
            const uint32_t end_row = id >> kItemRow1Shift & kItemRowMask;
            const uint32_t byte_offset = first_row * kRowBytes;
            const uint32_t bytes =
                (end_row > 0 ? (end_row - first_row) * kRowBytes : kOutPageBytes);
            if (!reader.reserve(planes, kShowPlanes)) {
                return false;
            }
            const uint32_t destination = get_write_ptr(planes) + byte_offset;
            // a tile's five planes lie in one tensor (its pages a multiple of five)
            const InterleavedAddrGen<true> frame_tensor = {
                .bank_base_address = bases[page / tensor_pages],
                .page_size = kOutPageBytes
            };
            for (uint32_t plane = 0; plane < count; ++plane) {
                noc_async_read(
                    get_noc_addr(
                        (page + first + plane) % tensor_pages, frame_tensor, byte_offset
                    ),
                    destination + plane * kShowPageBytes,
                    bytes
                );
            }
            if (!arrived(reader, command)) {
                return false;
            }
            cb_push_back(planes, kShowPlanes);
            return true;
        }
    };

}  // namespace show_k
