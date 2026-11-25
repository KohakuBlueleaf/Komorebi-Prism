// Lit SHADE on the pack thread (the camera's word not 0): each item's surface planes
// and material word, out in three parts; merging, the opaque layer's where it loses.
#pragma once

#include <stdint.h>

#include "../../../../../../core/include/texel_pages/space.hpp"

#include "../../../../../../core/include/grid.h"
#include "../copy_in.hpp"
#include "../list.hpp"
#include "merge.hpp"
#include "records.hpp"
#include "texels.hpp"

namespace shade_k {

    using light_k::kLwHashKeys;
    using light_k::kLwHashSlots;

    // The lit space's winners at `work`, the empty pixels' slot set.
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

    // Lit SHADE of one command: `opaque` the opaque layer's directory (0: not merging),
    // `grid` the frame's (grid.h); the records keying three textures, each winner's
    // slot filled once.
    [[gnu::noinline]] inline void shade_lit(
        const compute_mail::Waits& waits, uint32_t opaque, uint32_t grid
    ) {
        Counters counters;
        uint32_t* values = counters.values;
        const uint32_t started = km::wall();
        const bool merging = opaque != 0;
        const uint32_t item_pages = merging ? 2 * kPlanes : kPlanes;
        pack_sfpu::setup();
        bool succeeded = true;
        const uint32_t table_address = compute_mail::front(waits, kFieldFrameTable, 1);
        Table table;
        if (!table.at(table_address)) {
            compute_mail::stop(waits.stops, kGaveBadItem, kWhereShadeBad);
            succeeded = false;
        }
        const float* cam = reinterpret_cast<const float*>(table.words + kTabCamera);
        const uint32_t slots_address = texel_space::texel_slots(
            compute_mail::write_ptr(kFieldCommandSpace)
        );
        *reinterpret_cast<volatile uint32_t*>(
            slots_address + kShadeSlots * kTexPageBytes
        ) = 0xFFFFFFFF;  // the white texel
        texel_pages::Pages pages;
        pages.place(
            reinterpret_cast<uint32_t*>(
                texel_space::texel_work(compute_mail::write_ptr(kFieldCommandSpace))
            ) +
            1024
        );
        uint32_t* work = reinterpret_cast<uint32_t*>(
            texel_space::pack_work(compute_mail::write_ptr(kFieldCommandSpace))
        );
        Winners winners = lit_winners(work);
        uint32_t* slot_offsets = work + kLwSlot;
        uint32_t* row_bits = work + kLwRow;
        List list{waits};
        const size_t vl = __riscv_vsetvl_e32m8(32);
        while (succeeded) {
            const volatile uint32_t* header = list.next();
            if (header == nullptr) {
                succeeded = false;
                break;
            }
            if (header[0] == kMarkEnd) {
                break;
            }
            const uint32_t tile = header[kHdrTile], records = header[kHdrCount];
            const int32_t first_row = header[kHdrRow0], end_row = header[kHdrRow1];
            if (!(0 <= first_row && first_row < end_row && end_row <= 32 &&
                  tile < kTileCapacity)) {
                compute_mail::stop(waits.stops, kGaveBadItem, kWhereShadeBad);
                succeeded = false;
                break;
            }
            uint32_t mark = km::wall();
            const uint32_t planes = compute_mail::front(
                waits, kFieldInPlanes, item_pages
            );
            if (planes == 0) {
                succeeded = false;
                break;
            }
            uint32_t now = km::wall();
            values[kShadeProfWaitIn] += now - mark;
            mark = now;
            const uint32_t* plane_words = reinterpret_cast<const uint32_t*>(planes);
            const uint32_t* opaque_words = reinterpret_cast<const uint32_t*>(
                opaque_after(planes)
            );
            copy_in(plane_words, opaque_words, first_row, end_row, merging, vl);
            // the winners: each pixel's slot from its triangle (the empty pixels' slot)
            item_winners(winners, first_row, end_row, row_bits, slot_offsets, vl);
            if (!merging && !compute_mail::pop(waits, kFieldInPlanes, kPlanes)) {
                succeeded = false;
                break;
            }
            now = km::wall();
            values[kShadeProfCopyIn] += now - mark;
            mark = now;
            TTI_SFPENCC(3, 0, 0, 10);
            TT_SFPLOADI(L7, kFloatB, 0);
            for (int32_t r = first_row; r < end_row; ++r) {
                divide_row(r);
                store(L7, kVecRed + r);  // no normal, no specular key
                store(L7, kVecGreen + r);
            }
            now = km::wall();
            values[kShadeProfDivide] += now - mark;
            mark = now;
            if (!lit_records(
                    list,
                    table,
                    winners,
                    cam,
                    records,
                    first_row,
                    end_row,
                    tile / grid_of(grid).across,
                    merging,
                    counters
                )) {
                succeeded = false;
                break;
            }
            tensix_sync();
            now = km::wall();
            values[kShadeProfRecord] += now - mark;
            if (!compute_mail::reserve(
                    waits, kFieldOutRing, kLitParts * kShadeOutPages
                )) {
                succeeded = false;
                break;
            }
            Parts parts;
            parts.place(compute_mail::write_ptr(kFieldOutRing));
            if (!lit_texels(
                    waits,
                    first_row,
                    end_row,
                    work,
                    pages,
                    table.words,
                    slots_address,
                    table.page_limit,
                    merging,
                    parts,
                    counters
                )) {
                succeeded = false;
                break;
            }
            mark = km::wall();
            const uint32_t first_word = kRowBytes / 4 * first_row;
            const uint32_t words = kRowBytes / 4 * (end_row - first_row);
            if (merging &&
                !lit_merge(
                    waits, parts, plane_words, opaque_words, first_word, words, vl
                )) {
                succeeded = false;
                break;
            }
            for (uint32_t part = 0; part < kLitParts; ++part) {
                compute_mail::push(
                    kFieldOutRing,
                    parts.page(part, kPlanes - 1) + 4 * (first_word + words - 1),
                    kShadeOutPages
                );
            }
            values[kShadeProfOut] += km::wall() - mark;
            values[kShadeProfTiles]++;
        }
        // the reader's end, the list's last page, the table back, the unpack thread's
        // end
        texel_pages::ask_end(waits, kFieldTexelAsks);
        list.end();
        if (table_address != 0) {
            compute_mail::pop(waits, kFieldFrameTable, 1);
        }
        compute_mail::end_mails();
        pack_sfpu::finish();
        if (succeeded) {
            profile_out(waits, counters, started);
        }
    }

}  // namespace shade_k
