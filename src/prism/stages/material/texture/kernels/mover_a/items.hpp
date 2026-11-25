// SHADE's mover A per item: the core's list pages into their buffer, then each item's
// five planes (merging, the opaque layer's five of its tile after them).
#pragma once

#include <stdint.h>

#include "directory.hpp"

namespace shade_k {

    using fill_k::kInPageBytes;
    using fill_k::kItemEmpty;
    using fill_k::kItemSlot;
    using fill_k::kOutPageBytes;
    using fill_k::kPlanes;

    // Mover A's walk of the core's list pages and items in one command.
    struct Items {
        const Directory& directory;
        uint32_t lists = 0;   // the lists tensor's address
        uint32_t opaque = 0;  // the opaque directory (0: not merging)
        bool lit = false;     // lit merging: each item's opaque surface after it
        uint32_t page = 0, item = 0;
        uint32_t part = 0;  // lit merging: 1, 2 the surface's frame next

        // The opaque surface's frame `part` (1, 2) of the current item, five pages;
        // false: a bad item or a read that gave up.
        template <typename Mover>
        bool surface_part(const Mover& mover) {
            const uint32_t* words = directory.surface + (kDirFrameMax + 1) * (part - 1);
            const uint32_t surface_page = (directory.words[kDirIds + item] &
                                           kItemSlot) *
                kPlanes;
            if (surface_page / words[0] >= kDirFrameMax) {
                return false;
            }
            cb_reserve_back(kFieldInPlanes, kPlanes);
            const InterleavedAddrGen<true> surface_tensor = {
                .bank_base_address = words[1 + surface_page / words[0]],
                .page_size = kOutPageBytes
            };
            for (uint32_t plane = 0; plane < kPlanes; ++plane) {
                noc_async_read(
                    get_noc_addr((surface_page + plane) % words[0], surface_tensor),
                    get_write_ptr(kFieldInPlanes) + plane * kOutPageBytes,
                    kOutPageBytes
                );
            }
            if (!texel_pages::reads_arrived(mover)) {
                return false;
            }
            cb_push_back(kFieldInPlanes, kPlanes);
            part = part == 1 ? 2 : 0;
            item += part == 0;
            return true;
        }

        // The next list page, when there is one and room for it. 1: read, 0: none
        // now, -1: the read gave up.
        template <typename Mover>
        int list_page(const Mover& mover) {
            if (page >= directory.pages ||
                !cb_pages_reservable_at_back(kFieldShadeLists, 1)) {
                return 0;
            }
            cb_reserve_back(kFieldShadeLists, 1);
            if (!read_page(
                    mover,
                    lists,
                    kInPageBytes,
                    directory.first + page,
                    get_write_ptr(kFieldShadeLists)
                )) {
                return -1;
            }
            cb_push_back(kFieldShadeLists, 1);
            ++page;
            return 1;
        }

        // The next item's planes (empty items skipped), when the ring has room; false:
        // a bad item or a read that gave up.
        template <typename Mover>
        bool planes(const Mover& mover) {
            const uint32_t item_pages = opaque != 0 ? 2 * kPlanes : kPlanes;
            if (part != 0) {
                return !cb_pages_reservable_at_back(kFieldInPlanes, kPlanes) ||
                    surface_part(mover);
            }
            while (
                item < directory.items &&
                (directory.words[kDirIds + item] & kItemEmpty) != 0
            ) {
                ++item;
            }
            if (item >= directory.items ||
                !cb_pages_reservable_at_back(kFieldInPlanes, item_pages)) {
                return true;
            }
            const uint32_t tensor_pages = directory.tensor_pages;
            const uint32_t* other = directory.opaque;
            const uint32_t
                tile_page = ((directory.words[kDirIds + item] & kItemSlot) * kPlanes);
            if (tile_page / tensor_pages >= kDirFrameMax ||
                (opaque != 0 && tile_page / other[0] >= kDirFrameMax)) {
                return false;
            }
            cb_reserve_back(kFieldInPlanes, item_pages);
            const InterleavedAddrGen<true> frame_tensor = {
                .bank_base_address = directory.words
                                         [kDirFrame + 1 + tile_page / tensor_pages],
                .page_size = kOutPageBytes
            };
            const uint32_t destination = get_write_ptr(kFieldInPlanes);
            for (uint32_t plane = 0; plane < kPlanes; ++plane) {
                noc_async_read(
                    get_noc_addr((tile_page + plane) % tensor_pages, frame_tensor),
                    destination + plane * kOutPageBytes,
                    kOutPageBytes
                );
            }
            if (opaque != 0) {
                // the second five pages, after the first in the ring: its write place
                // is a multiple of five pages (the opaque layer's command's items)
                uint32_t second = destination + kPlanes * kOutPageBytes;
                if (second >= get_local_cb_interface(kFieldInPlanes).fifo_limit) {
                    second -= get_local_cb_interface(kFieldInPlanes).fifo_size;
                }
                const InterleavedAddrGen<true> opaque_tensor = {
                    .bank_base_address = other[1 + tile_page / other[0]],
                    .page_size = kOutPageBytes
                };
                for (uint32_t plane = 0; plane < kPlanes; ++plane) {
                    noc_async_read(
                        get_noc_addr((tile_page + plane) % other[0], opaque_tensor),
                        second + plane * kOutPageBytes,
                        kOutPageBytes
                    );
                }
            }
            if (!texel_pages::reads_arrived(mover)) {
                return false;
            }
            for (uint32_t pushed = 0; pushed < item_pages; pushed += kPlanes) {
                cb_push_back(kFieldInPlanes, kPlanes);  // five at a time: none wraps
            }
            if (lit && opaque != 0) {
                part = 1;
            } else {
                ++item;
            }
            return true;
        }
    };

}  // namespace shade_k
