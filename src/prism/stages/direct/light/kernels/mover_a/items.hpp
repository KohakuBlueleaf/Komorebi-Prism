// LIGHT on mover A: an item's planes into the planes ring (the surface's ten, the
// frame's 1/z and material word; glass: the glass layer's, C and the merged 1/z) and
// its word to compute.
#pragma once

#include <stdint.h>

#include "../../../../../core/include/grid.h"
#include "../light.h"
#include "api/dataflow/dataflow_api.h"
#include "directories.hpp"

namespace light_k {

    using fill_k::kItemRow0Shift;
    using fill_k::kItemRow1Shift;
    using fill_k::kItemRowMask;
    using fill_k::kItemSlot;
    using fill_k::kOutPageBytes;

    // An item's sources: the surface's frames, the opaque frame, the glass frame.
    struct ItemSources {
        const SurfaceWords& surface;
        volatile tt_l1_ptr uint32_t* directory;  // the opaque directory's page
        const uint32_t* glass_frame;             // its frame words; glass only
        bool glass;
        uint32_t planes, items;  // the planes ring and the item words' buffers
    };

    // The source (0, 1 the surface's frames, 2 the opaque frame, 3 the glass frame)
    // and plane of the item's page `at`.
    inline void page_source(
        uint32_t at, bool glass, uint32_t& source, uint32_t& plane
    ) {
        source = at < 2 * kPlanes ? at / kPlanes : glass ? 3 : 2;
        plane =
            (at < 2 * kPlanes ? at % kPlanes : (at == 2 * kPlanes ? 0 : kPlanes - 1));
        if (at >= kLightGlassC) {  // C, then the merged 1/z
            source = 2;
            plane = at < kLightGlassDepth ? 1 + at - kLightGlassC : 0;
        }
    }

    // Item `item`'s planes read and pushed five at a time, then its word (room for
    // both known). False: a tile or frame word out of range, or a read gave up.
    template <typename Mover>
    bool read_item(
        const Mover& reader,
        const km_command_t& command,
        const ItemSources& from,
        uint32_t item
    ) {
        const uint32_t item_pages = from.glass ? kLightGlassPages : kLightItemPages;
        const uint32_t item_planes = from.glass ? kLightGlassPlanes : kLightItemPlanes;
        const uint32_t tensor_pages = from.directory[kDirFrame];
        const uint32_t id = from.directory[fill_k::kDirIds + item];
        const uint32_t tile = id & kItemSlot;
        const uint32_t page = tile * kPlanes;
        const uint32_t* first_words = from.surface.first();
        const uint32_t* second_words = from.surface.second();
        if (tile >= kTileCapacity || page / tensor_pages >= kDirFrameMax ||
            page / first_words[0] >= kDirFrameMax ||
            page / second_words[0] >= kDirFrameMax ||
            (from.glass && page / from.glass_frame[0] >= kDirFrameMax)) {
            return false;
        }
        const InterleavedAddrGen<true> tensors[4] = {
            {.bank_base_address = first_words[1 + page / first_words[0]],
             .page_size = kOutPageBytes},
            {.bank_base_address = second_words[1 + page / second_words[0]],
             .page_size = kOutPageBytes},
            {.bank_base_address = from.directory[kDirFrame + 1 + page / tensor_pages],
             .page_size = kOutPageBytes},
            {.bank_base_address =
                 (from.glass ? from.glass_frame[1 + page / from.glass_frame[0]] : 0),
             .page_size = kOutPageBytes}
        };
        const uint32_t tensor_size[4] = {
            first_words[0],
            second_words[0],
            tensor_pages,
            from.glass ? from.glass_frame[0] : 1
        };
        const uint32_t ring = get_local_cb_interface(from.planes).fifo_size;
        const uint32_t ring_end = get_local_cb_interface(from.planes).fifo_limit;
        cb_reserve_back(from.planes, item_pages);
        uint32_t destination = get_write_ptr(from.planes);
        for (uint32_t at = 0; at < item_planes; ++at) {
            uint32_t source = 0, plane = 0;
            page_source(at, from.glass, source, plane);
            noc_async_read(
                get_noc_addr((page + plane) % tensor_size[source], tensors[source]),
                destination,
                kOutPageBytes
            );
            destination += kOutPageBytes;
            if (destination >= ring_end) {
                destination -= ring;
            }
        }
        if (!read_done(reader, command.sequence)) {
            return false;
        }
        for (uint32_t pushed = 0; pushed < item_pages; pushed += kLightPart) {
            cb_push_back(from.planes, kLightPart);  // five at a time: none wraps
        }
        const uint32_t first_row = id >> kItemRow0Shift & kItemRowMask;
        const uint32_t end_row = id >> kItemRow1Shift & kItemRowMask;
        cb_reserve_back(from.items, 1);
        volatile tt_l1_ptr uint32_t* words = km::l1(get_write_ptr(from.items));
        words[0] = end_row > 0 ? first_row | end_row << 8 : 32u << 8;
        words[1] = tile;
        cb_push_back(from.items, 1);
        return true;
    }

}  // namespace light_k
