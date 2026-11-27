// The lit material of one layer of a tile on the pack CPU, its planes in L1: each
// pixel's winner and slot, its records' three keys as the pass streams them, the page
// passes, the surface planes; a masked layer's frame words and surface taken into the
// opaque layer's where it wins.
#pragma once

#include <stdint.h>

#include "../../../../../raster/steps/kernels/lists.hpp"
#include "../planes.hpp"
#include "../run.hpp"
#include "records.hpp"
#include "texels.hpp"

namespace material_step {

    using light_k::kLwHashKeys;
    using light_k::kLwHashSlots;
    using light_k::kLwRow;
    using light_k::kLwSlot;

    // The surface's two places in the plane frame.surface, kSurfacePlanes pages each:
    // the opaque layer's (the masked one merged into it), the glass layer's (a masked
    // layer's scratch before it).
    constexpr uint32_t kSurfaceOpaque = 0;
    constexpr uint32_t kSurfaceGlass = 1;
    constexpr uint32_t kSurfaces = 2;

    // Surface `which`'s first page in the plane whose first page is at `surface`.
    constexpr uint32_t surface_planes(uint32_t surface, uint32_t which) {
        return surface + which * kSurfacePlanes * kOutPageBytes;
    }

    // The lit work's winners at `work`, the empty pixels' slot set (as
    // pack/lit/lit.hpp's).
    inline Winners lit_winners(uint32_t* work) {
        Winners winners;
        winners.keys = work + kLwHashKeys;
        winners.slots = work + kLwHashSlots;
        winners.words = work + kLwSlots;
        uint32_t* empty = winners.words + kLitSlotWords * kLitSlotEmpty;
        empty[0] = 0xFFFFFFFF;
        for (uint32_t w = 1; w < kLitSlotWords; ++w) {
            empty[w] = 0;
        }
        return winners;
    }

    // One layer (`role`, `entries` slots in `list`) of the band, lit: its planes at
    // `plane` (its material word to their last page), the opaque layer's at `opaque`,
    // the surfaces at `surface`, the camera's words `cam`, the lit work at `work`.
    // False: gave up (recorded).
    template <typename List>
    inline bool lit_layer(
        List& list,
        uint32_t entries,
        Run& run,
        Role role,
        uint32_t plane,
        uint32_t opaque,
        uint32_t surface,
        uint32_t* work,
        const float* cam
    ) {
        const bool merging = role == kMasked;
        const uint32_t* plane_words = reinterpret_cast<const uint32_t*>(plane);
        const uint32_t* opaque_words = reinterpret_cast<const uint32_t*>(opaque);
        planes_in(
            plane_words, opaque_words, run.first_row, run.end_row, merging, run.vl
        );
        Winners winners = lit_winners(work);
        item_winners(
            winners, run.first_row, run.end_row, work + kLwRow, work + kLwSlot, run.vl
        );
        TTI_SFPENCC(3, 0, 0, 10);
        TT_SFPLOADI(L7, kFloatB, 0);
        for (int32_t r = run.first_row; r < run.end_row; ++r) {
            divide_row(r);
            store(L7, kVecRed + r);  // no normal, no specular key
            store(L7, kVecGreen + r);
        }
        const bool walked = lit_records(
            list,
            run.table,
            winners,
            cam,
            entries,
            run.first_row,
            run.end_row,
            run.tile_y,
            merging,
            run.counters
        );
        if (!list.end_walk() || !walked) {
            return false;
        }
        tensix_sync();
        // the frame's words in the layer's own planes; the surface the opaque one's,
        // the glass one's (a masked layer's scratch: taken into the opaque one's below)
        const uint32_t own = surface_planes(
            surface, role == kOpaque ? kSurfaceOpaque : kSurfaceGlass
        );
        const Parts parts = {{plane, own, own + kPlanes * kOutPageBytes}};
        if (!lit_texels(
                run.waits,
                run.requests,
                run.first_row,
                run.end_row,
                work,
                run.pages,
                run.table.words,
                run.slots_address,
                run.table.page_limit,
                merging,
                parts,
                run.counters
            )) {
            return false;
        }
        if (merging) {  // 1/z and the material word, then the surface, where it takes
            take_page_rows(opaque, plane, 0, run.first_word, run.words, run.vl);
            take_page_rows(
                opaque, plane, kPlanes - 1, run.first_word, run.words, run.vl
            );
            const uint32_t merged = surface_planes(surface, kSurfaceOpaque);
            for (uint32_t page = 0; page < kSurfacePlanes; ++page) {
                take_page_rows(merged, own, page, run.first_word, run.words, run.vl);
            }
        }
        landed(
            (merging ? surface_planes(surface, kSurfaceOpaque) : own) +
            4 * ((kSurfacePlanes - 1) * kPlaneWords + run.first_word + run.words - 1)
        );
        run.counters.values[kShadeProfTiles]++;
        return true;
    }

}  // namespace material_step
