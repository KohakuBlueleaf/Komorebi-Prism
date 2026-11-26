// LIGHT on the pack CPU: each item's word, its planes a quarter tile at a time into
// Dst, keys, pages and texels, colour, out to the out pages' planes 1 to 3; the
// profile.
#pragma once

#include <stdint.h>

#include "../../../../../core/include/texel_pages/space.hpp"

#include "../../../../../core/include/grid.h"
#include "../waits.hpp"
#include "quarter.hpp"

namespace light_k {

    // The buffers LIGHT's pack CPU uses: the table page, items' words, the planes
    // ring, the out pages, the slots, the ask and done pages, the two works.
    struct PackBuffers {
        uint32_t table, items, planes, out, slots, ask, done, shade_work, light_work;
    };

    // The command's numbers from its table page; false: out of range (given up).
    inline bool command_numbers(
        const Waits& waits, const uint32_t* table, uint32_t mode, LightNumbers& numbers
    ) {
        const uint32_t* shade_table = table + kLightShadeTableAt;
        numbers.terms = table[kLtTerms];
        numbers.lamps = table[kLtLamps];
        numbers.bits = table[kLtExponentBits];
        numbers.graded = table[kLtSaturation] != kOneBits ||
            table[kLtCurve] != kCurvePlain;
        if (numbers.lamps > kLampsMax || numbers.bits > 11 ||
            table[kLtCurve] > kCurveFilmic || mode > kLightGlass ||
            (mode == kLightGlass &&
             kTabMaterial + kMaterialWords * shade_table[kTabMaterials] >
                 kLightShadeTableBytes / 4)) {
            compute_mail::stop(waits.stops, waits.stops.gave_bad, kWhereLightBad);
            return false;
        }
        return true;
    }

    // The profile item: the counts after the command's items (the total's time once
    // its page is reserved), its page pushed.
    inline void profile_out(
        const Waits& waits, uint32_t out, uint32_t started, uint32_t* values
    ) {
        if (!compute_mail::reserve(waits, out, kLightOutPages)) {
            return;
        }
        values[kLightProfTotal] = km::wall() - started;
        volatile uint32_t* profile = reinterpret_cast<volatile uint32_t*>(
            compute_mail::write_ptr(out)
        );
        for (uint32_t i = 0; i < kLightProfBytes / 4; ++i) {
            profile[i] = i < kLightProfWords ? values[i] : 0;
        }
        compute_mail::push(
            out,
            reinterpret_cast<uint32_t>(profile) + kLightProfBytes - 4,
            kLightOutPages
        );
    }

    // The counts of the page passes into the profile's words.
    inline void pass_counts(const Pass& pass, uint32_t* values) {
        values[kLightProfScan] = pass.counts.scan;
        values[kLightProfWaitPages] = pass.counts.wait;
        values[kLightProfPasses] = pass.counts.passes;
        values[kLightProfPages] = pass.counts.pages;
        // the field's scan less its keys (field_scan times both)
        values[kLightProfFieldScan] = pass.field_counts.scan -
            values[kLightProfFieldKeys];
        values[kLightProfFieldWait] = pass.field_counts.wait;
        values[kLightProfFieldPasses] = pass.field_counts.passes;
        values[kLightProfFieldPages] = pass.field_counts.pages;
    }

    // LIGHT of one command; `mode` its form (kLight*), `bank_grid` the grid's word.
    inline void pack_command(
        const Waits& waits,
        const PackBuffers& buffers,
        uint32_t bank_grid,
        uint32_t mode
    ) {
        const uint32_t started = km::wall();
        setup();
        bool succeeded = true;
        const uint32_t table_address = compute_mail::front(waits, buffers.table, 1);
        const uint32_t* table = reinterpret_cast<const uint32_t*>(table_address);
        const bool glass = mode == kLightGlass;
        Pass pass = {
            waits, buffers.ask, buffers.done, table, {table, 0, 0, 0, mode, false}
        };
        pass.cam = table + kLtCamera;
        pass.glass = glass;
        // glass: SHADE's materials after LIGHT's table (mover_a/table.hpp)
        const uint32_t* material_words = table + kLightShadeTableAt + kTabMaterial;
        succeeded = table_address != 0 &&
            command_numbers(waits, table, mode, pass.numbers);
        const uint32_t item_pages = glass ? kLightGlassPages : kLightItemPages;
        const uint32_t terms = pass.numbers.terms;
        const bool keyed = succeeded && (terms & (kTermShadow | kTermBackground)) != 0;
        const bool pointed = (terms & (kTermLamps | kTermSpecular)) != 0;
        const bool field = succeeded && (terms & kTermIndirect) != 0;
        pass.page_limit = succeeded ? table[kLtPages] : 0;
        const uint32_t slots_address = texel_space::texel_slots(
            compute_mail::write_ptr(buffers.slots)
        );
        // the zero texel of each field direction's place (a key of 0)
        for (uint32_t direction = 0; direction < 6; ++direction) {
            *reinterpret_cast<volatile uint32_t*>(
                slots_address + kZeroTexel + kFieldDirectionBytes * direction
            ) = 0;
        }
        uint32_t* shade_work = reinterpret_cast<uint32_t*>(
            texel_space::texel_work(compute_mail::write_ptr(buffers.shade_work))
        );
        pass.pages.place(shade_work + kLightPagesAt);
        uint32_t* work = reinterpret_cast<uint32_t*>(
            texel_space::pack_work(compute_mail::write_ptr(buffers.light_work))
        );
        uint32_t* values = work + kLwProfile;
        for (uint32_t i = 0; i < kLightProfWords; ++i) {
            values[i] = 0;
        }
        pass.values = values;
        pass.index = work + kLwIndex;
        pass.field_index = work + kLwField;
        pass.slots = reinterpret_cast<const uint32_t*>(slots_address);
        const size_t vl = __riscv_vsetvl_e32m8(32);
        pass.vl = vl;
        if (succeeded) {
            // the lanes' column + 0.5, 1 / f
            for (uint32_t lane = 0; lane < 32; ++lane) {
                window()[word(kLvLane) + 2 * lane] = as_bits(
                    static_cast<float>(lane) + 0.5f
                );
            }
            setup_k::setup_pass::order(word(kLvLane) + 62);
            TTI_SFPENCC(3, 0, 0, 10);
            immediate(L0, pass.cam[12]);
            recip(L0, L1, L2, L3, L4, L5);
            store(L1, kLvInvF);
        }
        while (succeeded) {
            uint32_t mark = km::wall();
            const uint32_t answer = compute_mail::front(waits, buffers.items, 1);
            if (answer == 0) {
                succeeded = false;
                break;
            }
            const uint32_t rows = reinterpret_cast<const volatile uint32_t*>(answer)[0];
            const uint32_t tile = reinterpret_cast<const volatile uint32_t*>(answer)[1];
            if (!compute_mail::pop(waits, buffers.items, 1)) {
                succeeded = false;
                break;
            }
            if (rows == kShadeAskEnd) {
                break;
            }
            const uint32_t first_row = rows & 0xFF, end_row = rows >> 8 & 0xFF;
            if (!(first_row < end_row && end_row <= 32 && tile < kTileCapacity)) {
                compute_mail::stop(waits.stops, waits.stops.gave_bad, kWhereLightBad);
                succeeded = false;
                break;
            }
            const uint32_t planes = compute_mail::front(
                waits, buffers.planes, item_pages
            );
            if (planes == 0 ||
                !compute_mail::reserve(waits, buffers.out, kLightOutPages)) {
                succeeded = false;
                break;
            }
            const uint32_t out = compute_mail::write_ptr(buffers.out);
            uint32_t now = km::wall();
            values[kLightProfWait] += now - mark;
            const uint32_t limit = get_local_cb_interface(buffers.planes).fifo_limit
                << 4;
            const uint32_t size = get_local_cb_interface(buffers.planes).fifo_size << 4;
            const uint32_t across = grid_of(bank_grid).across;  // grid.h
            const uint32_t tile_x = tile % across;
            pass.tile_y = tile / across;
            TTI_SFPENCC(3, 0, 0, 10);
            load(L0, kLvLane);
            immediate(L1, setup_k::float_bits(32 * tile_x));
            add(L0, L1, L0);
            immediate(L1, pass.cam[13]);
            sub(L0, L1, L0);
            over_focal(L0, L2, L3, L4, pass.cam[12]);
            store(L2, kLvXTerm);
            const uint32_t item_field_pages = pass.field_counts.pages;
            for (
                uint32_t quarter = 0; quarter < 32 / kLightRows && succeeded; ++quarter
            ) {
                const uint32_t row0 = kLightRows * quarter;
                pass.row0 = row0;
                pass.first = first_row > row0 ? first_row : row0;
                pass.end = end_row < row0 + kLightRows ? end_row : row0 + kLightRows;
                if (pass.first >= pass.end) {
                    continue;
                }
                mark = km::wall();
                copy_in(planes, quarter, limit, size, vl);
                // glass: in front where, w a, tau C (glass_in)
                const bool in_front =
                    (glass &&
                     glass_in(planes, quarter, material_words, limit, size, vl));
                setup_k::setup_pass::order(
                    glass ? word(c_vector(2, kLightRows - 1)) + 62
                          : kQuarterWords * kLvPlanes - 1
                );
                now = km::wall();
                values[kLightProfCopyIn] += now - mark;
                pass.mark = now;
                if (!quarter_colour(pass, in_front, keyed, pointed, field)) {
                    succeeded = false;
                    break;
                }
                mark = km::wall();
                copy_out(out, quarter, vl);
                values[kLightProfOut] += km::wall() - mark;
            }
            if (!succeeded) {
                break;
            }
            const uint32_t item_pages_read = pass.field_counts.pages - item_field_pages;
            if (item_pages_read > values[kLightProfFieldItemPages]) {
                values[kLightProfFieldItemPages] = item_pages_read;
            }
            // popped five pages at a time, as pushed (mover_a/items.hpp)
            for (
                uint32_t popped = 0; popped < item_pages && succeeded;
                popped += kLightPart
            ) {
                succeeded = compute_mail::pop(waits, buffers.planes, kLightPart);
            }
            if (!succeeded) {
                break;
            }
            compute_mail::push(
                buffers.out,
                out + (kLightFirstPlane + kLightColourPlanes) * kOutPageBytes - 4,
                kLightOutPages
            );
            values[kLightProfTiles]++;
        }
        pass_counts(pass, values);
        // the reader's end, the table back, the unpack thread's end
        ask_end(waits, buffers.ask);
        if (table_address != 0) {
            compute_mail::pop(waits, buffers.table, 1);
        }
        compute_mail::end_mails();
        finish();
        if (succeeded) {
            profile_out(waits, buffers.out, started, values);
        }
    }

    // The handler's pack CPU: its buffers by the class's header, its words.
    inline void light_pack(
        km::Compute& compute,
        const km_command_t& command,
        uint32_t table,
        uint32_t shade_table,
        uint32_t camera,
        uint32_t bank_grid,
        uint32_t mode
    ) {
        static_cast<void>(command);
        static_cast<void>(table);
        static_cast<void>(shade_table);
        static_cast<void>(camera);
        const Waits waits = waits_of(compute.control());
        const PackBuffers buffers = {
            kFieldFrameTable,
            kFieldItems,
            kFieldInPlanes,
            kFieldOutRing,
            kFieldCommandSpace,
            kFieldTexelAsks,
            kFieldTexelDones,
            kFieldCommandSpace,
            kFieldCommandSpace
        };
        pack_command(waits, buffers, bank_grid, mode & ~kLightShown);
    }

}  // namespace light_k
