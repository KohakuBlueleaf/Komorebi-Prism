// SHADE on the pack thread: each item of the core's list coloured in Dst (u, v, light,
// texel keys, pages, texels, colour), merged or blended with the opaque layer's, out.
#pragma once

#include <stdint.h>

#include "../../../../../core/include/texel_pages/space.hpp"

#include "blend.hpp"
#include "colour.hpp"
#include "copy_in.hpp"
#include "keys.hpp"
#include "lit/lit.hpp"
#include "list.hpp"
#include "texels.hpp"

namespace shade_k {

    // An item's records into Dst rows [first_row, end_row) of `tile_y`'s tile: their
    // keys, colours and marks; false when the list gave up.
    inline bool item_records(
        List& list,
        const Table& table,
        uint32_t records,
        int32_t first_row,
        int32_t end_row,
        uint32_t tile_y,
        bool merging,
        bool glass,
        Counters& counters
    ) {
        for (uint32_t record_index = 0; record_index < records; ++record_index) {
            const volatile uint32_t* record = list.next();
            if (record == nullptr) {
                return false;
            }
            const uint32_t shade_word = record[kRecShade];
            const uint32_t material = shade_word & 0xFFFF;
            const uint32_t level = shade_word >> kShadeLevelShift & 0xF;
            const int32_t
                box_first = (static_cast<int32_t>(record[kRecY0]) - 32 * tile_y);
            const int32_t box_last = static_cast<int32_t>(record[kRecY1]) - 32 * tile_y;
            const int32_t row_first = box_first < first_row ? first_row : box_first;
            const int32_t row_last = box_last > end_row - 1 ? end_row - 1 : box_last;
            if (material >= table.materials || row_first > row_last) {
                continue;  // no material: FILL's colour divided by 1/z (flat)
            }
            uint32_t numbers[kRecordNumbers];
            const Mode mode = record_mode(
                table, record[kRecTri], material, level, merging, numbers
            );
            if (mode == kFlat) {
                continue;  // FILL's colour divided by 1/z, no texel
            }
            record_numbers(numbers);
            // the glass layer's pixels keep their material for the blend
            const uint32_t mark_bits = glass ? kMinusTwo | material : kMinusTwo;
            for (int32_t r = row_first; r <= row_last; ++r) {
                record_row(r, mode, kVecDepth, true, true, mark_bits);
                counters.values[kShadeProfRows]++;
            }
            counters.values[kShadeProfRecords]++;
        }
        return true;
    }

    // SHADE on the pack CPU: `opaque` the opaque layer's directory (0: not merging),
    // `mode` the kShade* bits, `grid` the frame's (grid.h), `camera` the camera's
    // address (0: unlit; else the lit form, lit/lit.hpp).
    inline void shade_pack(
        km::Compute& compute,
        const km_command_t& command,
        uint32_t opaque,
        uint32_t mode,
        uint32_t grid,
        uint32_t camera
    ) {
        static_cast<void>(command);
        const compute_mail::Waits waits = waits_of(compute.control());
        if (camera != 0) {
            shade_lit(waits, opaque, grid);
            return;
        }
        Counters counters;
        uint32_t* values = counters.values;
        const uint32_t started = km::wall();
        // the masked or glass layer's: its planes, then the opaque layer's;
        // kShadeGlass blends, kShadeMergedDepth also gives the merged 1/z
        const bool merging = opaque != 0;
        const bool glass = merging && (mode & kShadeGlass) != 0;
        const bool merged_depth = merging && !glass && (mode & kShadeMergedDepth) != 0;
        const uint32_t item_pages = merging ? 2 * kPlanes : kPlanes;
        pack_sfpu::setup();
        bool succeeded = true;
        const uint32_t table_address = compute_mail::front(waits, kFieldFrameTable, 1);
        Table table;
        if (!table.at(table_address)) {
            compute_mail::stop(waits.stops, kGaveBadItem, kWhereShadeBad);
            succeeded = false;
        }
        const uint32_t slots_address = texel_space::texel_slots(
            compute_mail::write_ptr(kFieldCommandSpace)
        );
        *reinterpret_cast<volatile uint32_t*>(
            slots_address + kShadeSlots * kTexPageBytes
        ) = 0xFFFFFFFF;  // the white texel: albedo 1
        uint32_t* work = reinterpret_cast<uint32_t*>(
            texel_space::texel_work(compute_mail::write_ptr(kFieldCommandSpace))
        );
        uint32_t* index = work;  // 1,024 texel addresses, row by row
        texel_pages::Pages pages;
        pages.place(work + 1024);
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
            if (!merging && !compute_mail::pop(waits, kFieldInPlanes, kPlanes)) {
                succeeded = false;
                break;
            }
            now = km::wall();
            values[kShadeProfCopyIn] += now - mark;
            mark = now;
            for (int32_t r = first_row; r < end_row; ++r) {
                divide_row(r);
            }
            now = km::wall();
            values[kShadeProfDivide] += now - mark;
            mark = now;
            const uint32_t tile_y = tile / grid_of(grid).across;
            if (!item_records(
                    list,
                    table,
                    records,
                    first_row,
                    end_row,
                    tile_y,
                    merging,
                    glass,
                    counters
                )) {
                succeeded = false;
                break;
            }
            tensix_sync();
            now = km::wall();
            values[kShadeProfRecord] += now - mark;
            if (!texels(
                    waits,
                    first_row,
                    end_row,
                    index,
                    pages,
                    table.gamma,
                    slots_address,
                    table.page_limit,
                    merging && !glass,  // the masks' (the glass layer has none)
                    counters
                )) {
                succeeded = false;
                break;
            }
            mark = km::wall();
            colour_rows(first_row, end_row);
            if (!compute_mail::reserve(waits, kFieldOutRing, kShadeOutPages)) {
                succeeded = false;
                break;
            }
            const uint32_t destination = compute_mail::write_ptr(kFieldOutRing);
            const uint32_t first_word = kRowBytes / 4 * first_row;
            const uint32_t words = kRowBytes / 4 * (end_row - first_row);
            colour_out(destination, first_word, words);
            if (glass) {  // tau C + (1 - max tau) colour where marked, else C
                glass_blend(
                    destination,
                    opaque_words,
                    table.material_words,
                    first_word,
                    words,
                    vl
                );
            } else if (merging) {  // the opaque layer's colour where the depth row is
                                   // not 1
                masked_merge(
                    destination,
                    plane_words,
                    opaque_words,
                    first_word,
                    words,
                    merged_depth,
                    vl
                );
            }
            compute_mail::push(
                kFieldOutRing,
                destination +
                    4 *
                        ((kShadeColourPages - 1) * kPlaneWords + first_word + words -
                         1),
                kShadeOutPages
            );
            if (merging &&
                (!compute_mail::pop(waits, kFieldInPlanes, kPlanes) ||
                 !compute_mail::pop(waits, kFieldInPlanes, kPlanes))) {
                succeeded = false;
                break;
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
