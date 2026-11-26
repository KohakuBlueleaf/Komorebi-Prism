// LIGHT on mover B, shown (kLightShown): the thresholds read once a command, then each
// item's colour planes in the out ring converted by SHOW's writer into a scratch page
// and its rows written to its tile's page of the display.
#pragma once

#include <stdint.h>

#include "../../../../../core/include/grid.h"
#include "../../../../../core/include/surface.h"
#include "../../../../post/show/kernels/write.hpp"
#include "../light.h"
#include "komorebi/device/tensors/km_ask.hpp"
#include "sends.hpp"

namespace light_k {

    // The display's words of a command (the surface's directory page), SHOW's writer.
    struct Shown {
        show_k::Writer show;
        uint32_t display = 0;  // the display tensor's address
        uint32_t pages = 0;    // its pages
    };

    // The display's words from the surface's directory page at `directory`, the
    // thresholds' table read into `scratch` (the bank of `bank_grid`) and the buckets
    // made in the scratch pages. False: gave up.
    template <typename Mover>
    bool shown_start(
        const Mover& writer,
        const km_command_t& command,
        const volatile tt_l1_ptr uint32_t* directory,
        uint32_t scratch,
        uint32_t bank_grid,
        Shown& shown
    ) {
        shown.display = directory[kSurfaceShowDisplay];
        shown.pages = directory[kSurfaceShowPages];
        const uint32_t table = directory[kSurfaceShowTable];
        if (shown.display == 0 || table == 0) {
            return shown.show.bad(writer, command);
        }
        const km::BankRange region(
            table, bank_word(bank_grid) - 1, show_k::kShowPageBytes
        );
        if (!km::read_pages(writer, command, region, 0, 1, scratch) ||
            !writer_read_done(writer, command.sequence)) {
            return false;
        }
        shown.show.start(0, get_write_ptr(kFieldShownScratch));
        shown.show.table(scratch);
        return true;
    }

    // Item `id`'s rows [first_row, end_row) of the colour planes from `red` (green,
    // blue after it) converted into a scratch page and written to page tile of the
    // display, as show_k::Writer::item with first 0, across kGridDefault. False: gave
    // up.
    template <typename Mover>
    bool shown_item(
        const Mover& writer,
        const km_command_t& command,
        Shown& shown,
        uint32_t id,
        uint32_t red
    ) {
        show_k::Writer& show = shown.show;
        const uint32_t tile = id & fill_k::kItemSlot;
        const uint32_t page = tile / kGridDefault * kGridDefault + tile % kGridDefault;
        if (page >= shown.pages) {
            return show.bad(writer, command);
        }
        const uint32_t first_row = id >> fill_k::kItemRow0Shift & fill_k::kItemRowMask;
        const uint32_t row_end = id >> fill_k::kItemRow1Shift & fill_k::kItemRowMask;
        const uint32_t end_row = row_end > 0 ? row_end : 32;
        const uint32_t byte_offset = first_row * fill_k::kRowBytes;
        const uint32_t asked = km::wall();
        const uint32_t out = show.scratch + (show.done++ & 1) * show_k::kShowPageBytes;
        if (!show.sent(writer, command)) {  // the page's last write left
            return false;
        }
        const uint32_t ready = km::wall();
        invalidate_l1_cache();
        // plain loads and stores: the planes stay put until the pop, the page until
        // its write is sent
        const tt_l1_ptr uint32_t* planes = reinterpret_cast<const tt_l1_ptr uint32_t*>(
            red
        );
        tt_l1_ptr uint32_t* pixels = reinterpret_cast<tt_l1_ptr uint32_t*>(out);
        show_k::colour_rows(
            planes, pixels, first_row, end_row, show.thresholds, show.buckets()
        );
        const uint32_t converted = km::wall();
        const InterleavedAddrGen<true> display = {
            .bank_base_address = shown.display, .page_size = show_k::kShowPageBytes
        };
        noc_async_write(
            out + byte_offset,
            get_noc_addr(page, display, byte_offset),
            (end_row - first_row) * fill_k::kRowBytes
        );
        show.convert += converted - ready;
        show.write += (ready - asked) + (km::wall() - converted);
        show.rows += end_row - first_row;
        ++show.items;
        return true;
    }

    // The last display writes sent, then mover B's words into the profile page at
    // `profile`. False: gave up.
    template <typename Mover>
    bool shown_profile(
        const Mover& writer,
        const km_command_t& command,
        const Shown& shown,
        uint32_t profile
    ) {
        if (!shown.show.sent(writer, command)) {
            return false;
        }
        volatile tt_l1_ptr uint32_t* words = km::l1(profile);
        words[kLightProfShowConvert] = shown.show.convert;
        words[kLightProfShowWrite] = shown.show.write;
        words[kLightProfShowRows] = shown.show.rows;
        words[kLightProfShowItems] = shown.show.items;
        return true;
    }

}  // namespace light_k
