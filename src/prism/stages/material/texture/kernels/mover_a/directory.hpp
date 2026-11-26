// SHADE's mover A at a command's start: the core's directory page (and, merging, the
// opaque layer's frame words from its own), then the table pushed to the pack thread.
#pragma once

#include <stdint.h>

#include "../../../../../core/include/texel_pages/ask.hpp"
#include "../../../../../core/include/grid.h"
#include "../../../../raster/kernels/common/layouts.hpp"
#include "../shade.h"

namespace shade_k {

    // the surface's directory words of mover A and of mover B: the common own pages
    constexpr uint32_t kDirA = kFieldOwnPage1;
    constexpr uint32_t kDirB = kFieldOwnPage2;

    using fill_k::kDirBytes;
    using fill_k::kDirFirst;
    using fill_k::kDirFrame;
    using fill_k::kDirFrameMax;
    using fill_k::kDirIds;
    using fill_k::kDirItems;
    using fill_k::kDirMaxItems;
    using fill_k::kDirPages;

    // Page `page` (of `bytes`) of the interleaved tensor at `base` into L1 `to`;
    // false: the read did not arrive.
    template <typename Mover>
    bool read_page(
        const Mover& mover, uint32_t base, uint32_t bytes, uint32_t page, uint32_t to
    ) {
        const InterleavedAddrGen<true> tensor = {
            .bank_base_address = base, .page_size = bytes
        };
        noc_async_read(get_noc_addr(page, tensor), to, bytes);
        return texel_pages::reads_arrived(mover);
    }

    // A core's directory page as mover A reads it: its list pages and items, its frame
    // words; merging, the opaque layer's frame words; lit, the surface's two frames'.
    struct Directory {
        volatile tt_l1_ptr uint32_t* words = nullptr;
        uint32_t first = 0, pages = 0, items = 0, tensor_pages = 0;
        uint32_t opaque[kDirFrameMax + 1] = {};
        uint32_t surface[kSurfaceWords] = {};

        // The surface directory's page (`address`) at `scratch`: both frames' words;
        // false: the read gave up. `valid` false: not two frames of five planes.
        template <typename Mover>
        bool read_surface(
            const Mover& mover,
            uint32_t address,
            uint32_t page,
            uint32_t scratch,
            bool& valid
        ) {
            if (!read_page(mover, address, kDirBytes, page, scratch)) {
                return false;
            }
            invalidate_l1_cache();
            volatile tt_l1_ptr uint32_t* given = km::l1(scratch);
            for (uint32_t i = 0; i <= kDirFrameMax; ++i) {
                surface[i] = given[kDirFrame + i];
                surface[kDirFrameMax + 1 + i] = given[kSurfaceSecond + i];
            }
            valid = surface[0] != 0 && surface[0] % fill_k::kPlanes == 0 &&
                surface[kDirFrameMax + 1] != 0 &&
                surface[kDirFrameMax + 1] % fill_k::kPlanes == 0;
            return true;
        }

        // The opaque layer's page (`opaque_address`, 0: none) then the core's own at
        // `scratch`; false: a read gave up. `valid` false: not a frame of planes.
        template <typename Mover>
        bool read(
            const Mover& mover,
            uint32_t address,
            uint32_t opaque_address,
            uint32_t page,
            uint32_t scratch,
            bool& valid
        ) {
            words = km::l1(scratch);
            if (opaque_address != 0) {
                if (!read_page(mover, opaque_address, kDirBytes, page, scratch)) {
                    return false;
                }
                invalidate_l1_cache();
                for (uint32_t i = 0; i <= kDirFrameMax; ++i) {
                    opaque[i] = words[kDirFrame + i];
                }
            }
            if (!read_page(mover, address, kDirBytes, page, scratch)) {
                return false;
            }
            invalidate_l1_cache();
            first = words[kDirFirst];
            pages = words[kDirPages];
            items = words[kDirItems];
            tensor_pages = words[kDirFrame];
            valid = tensor_pages != 0 && tensor_pages % fill_k::kPlanes == 0 &&
                items <= kDirMaxItems &&
                (opaque_address == 0 ||
                 (opaque[0] != 0 && opaque[0] % fill_k::kPlanes == 0));
            return true;
        }
    };

    // SHADE's table (page 0 of the tensor at `table_address`) into its buffer, lit
    // (`camera` not 0) the camera after its words (in the bank of `grid`), pushed;
    // false: no room or the read gave up.
    template <typename Mover>
    bool push_table(
        const Mover& mover, uint32_t table_address, uint32_t camera, uint32_t grid
    ) {
        static_assert(kShadeTableBytes == kFieldFrameTablePageBytes);
        if (!mover.reserve(kFieldFrameTable, 1)) {
            return false;
        }
        const InterleavedAddrGen<true> tensor = {
            .bank_base_address = table_address, .page_size = kShadeTableBytes
        };
        noc_async_read(
            get_noc_addr(0, tensor), get_write_ptr(kFieldFrameTable), kShadeTableBytes
        );
        if (camera != 0) {
            noc_async_read_barrier();
            noc_async_read(
                get_noc_addr_from_bank_id<true>(bank_word(grid) - 1, camera),
                get_write_ptr(kFieldFrameTable) + 4 * kTabCamera,
                4 * kCamWordsShade
            );
        }
        if (!texel_pages::reads_arrived(mover)) {
            return false;
        }
        cb_push_back(kFieldFrameTable, 1);
        return true;
    }

}  // namespace shade_k
