// SHOW's view transform in its class: mover A hands each item's id and planes (then
// the end) to the pack CPU, which takes the planes through view_fetch.hpp in place and
// hands mover B a token, the cube's pages asked of mover A (texel_pages' asks and
// dones, an ask's end closing an item); the unpack CPU serves the pack CPU's mails.
#pragma once

#include <stdint.h>

#include "../../../raster/kernels/common/layouts.hpp"
#include "view.h"

#if defined(TRISC_PACK) || defined(TRISC_UNPACK)
#include "../../../../core/include/compute_mail.hpp"
#endif
#include "../../../../core/include/texel_pages/protocol.h"
#if defined(TRISC_PACK)
#include "view_fetch.hpp"
#endif
#if !defined(COMPILE_FOR_TRISC)
#include "../../../../core/include/texel_pages/ask.hpp"
#endif

namespace show_view {

    // An item's planes (show.h kShowPlanes) and their rows' words.
    constexpr uint32_t kItemPlanes = 3;
    constexpr uint32_t kItemsEnd = 0xFFFFFFFF;  // the item ids' last: the command's end
    static_assert(kViewSlots <= kShadeSlots);   // a pass's pages fit an ask
    // Give-up places (the writer's word): the pack CPU's mails, a buffer's front, a
    // bad item; mover A's service of the asks.
    constexpr uint32_t kWhereShowViewMail = 33;
    constexpr uint32_t kWhereShowViewFront = 34;
    constexpr uint32_t kWhereShowViewBad = 35;
    constexpr uint32_t kWhereShowViewAsks = 36;

    // The words [first, end) of the planes of the rows an item `id` holds (a row pair's
    // 64 words a pair; 32 rows: id's end row 0).
    inline void item_words(uint32_t id, uint32_t& first, uint32_t& end) {
        const uint32_t first_row = id >> fill_k::kItemRow0Shift & fill_k::kItemRowMask;
        const uint32_t row_end = id >> fill_k::kItemRow1Shift & fill_k::kItemRowMask;
        const uint32_t end_row = row_end > 0 ? row_end : 32;
        first = (first_row & ~1u) * fill_k::kRowBytes / 4;
        end = ((end_row + 1) & ~1u) * fill_k::kRowBytes / 4;
    }

#if defined(TRISC_PACK) || defined(TRISC_UNPACK)
    inline compute_mail::Waits waits_of(uint32_t control) {
        return {
            {control,
             fill_k::kGaveWait,
             fill_k::kGaveBadItem,
             kWhereShowViewMail,
             kWhereShowViewFront,
             kWhereShowViewBad},
            fill_k::kWaitCycles
        };
    }
#endif

#if defined(TRISC_PACK)
    // The pack CPU's state for one command: the view's words, the buffers, the slots
    // and work in the command space, the counts.
    struct Packer {
        compute_mail::Waits waits;
        const uint32_t* view;
        uint32_t viewed, asks, dones, slots, work, counted;
        view_fetch::ViewCounts counts;

        // The counts into the writer's place for its profile.
        void count() const {
            volatile uint32_t* to = reinterpret_cast<volatile uint32_t*>(counted);
            to[0] = counts.items;
            to[1] = counts.passes;
            to[2] = counts.pages;
        }

        // The pass's pages into the slots: an ask of mover A, its done waited for.
        bool ask(const uint32_t* pages, uint32_t count) {
            if (!compute_mail::reserve(waits, asks, 1)) {
                return false;
            }
            volatile uint32_t* page = reinterpret_cast<volatile uint32_t*>(
                compute_mail::write_ptr(asks)
            );
            page[0] = count;
            for (uint32_t i = 0; i < count; ++i) {
                page[1 + i] = pages[i];
            }
            compute_mail::push(asks, reinterpret_cast<uint32_t>(page + count), 1);
            return compute_mail::front(waits, dones, 1) != 0 &&
                compute_mail::pop(waits, dones, 1);
        }

        // Mover A's next words in `items` (two: an item's id and its planes' L1
        // address; first, on or off). False: gave up.
        bool next(uint32_t items, uint32_t& id, uint32_t& at) {
            const uint32_t page = compute_mail::front(waits, items, 1);
            if (page == 0) {
                return false;
            }
            id = reinterpret_cast<volatile uint32_t*>(page)[0];
            at = reinterpret_cast<volatile uint32_t*>(page)[1];
            return compute_mail::pop(waits, items, 1);
        }

        // The items mover A hands on in `items` converted, to their end, when its first
        // words say the view is on. False: gave up.
        bool items_of(uint32_t items) {
            uint32_t id = 0, at = 0;
            if (!next(items, id, at)) {
                return false;
            }
            for (bool on = id != 0; on;) {
                if (!next(items, id, at)) {
                    return false;
                }
                on = id != kItemsEnd;
                if (on && !item(id, at)) {
                    return false;
                }
            }
            return true;
        }

        // Item `id`'s planes at `at` through the view in place, its asks closed, a
        // token in `viewed` for the writer. False: gave up.
        bool item(uint32_t id, uint32_t at) {
            uint32_t first = 0, end = 0;
            item_words(id, first, end);
            float* planes = reinterpret_cast<float*>(at);
            const bool done = view_fetch::view_planes(
                view,
                planes,
                planes,
                first,
                end,
                reinterpret_cast<uint32_t*>(work),
                slots,
                [&](const uint32_t* pages, uint32_t count) {
                    return ask(pages, count);
                },
                counts
            );
            if (!done || !compute_mail::reserve(waits, asks, 1)) {
                return false;
            }
            const uint32_t close = compute_mail::write_ptr(asks);
            *reinterpret_cast<volatile uint32_t*>(close) = kShadeAskEnd;
            compute_mail::push(asks, close, 1);
            count();
            if (!compute_mail::reserve(waits, viewed, 1)) {
                return false;
            }
            const uint32_t token = compute_mail::write_ptr(viewed);
            *reinterpret_cast<volatile uint32_t*>(token) = id;
            compute_mail::push(viewed, at + 4 * (end - 1), 1);
            return true;
        }
    };
#endif

#if !defined(COMPILE_FOR_TRISC)
    // A mover's words of the view: on, the cube's pages' bank address.
    struct Served {
        bool on;
        uint32_t base;
    };

    // The view's words from the region `region` (its pages after the thresholds')
    // into L1 `to`: the first 64 bytes, all kViewRegionBytes when `whole` and on;
    // off when they do not arrive.
    template <typename Mover_, typename Region_>
    Served served_of(
        const Mover_& mover, const Region_& region, uint32_t to, bool whole
    ) {
        noc_async_read(region.get_noc_addr(1), to, 64);
        if (!texel_pages::reads_arrived(mover)) {
            return {false, 0};
        }
        const volatile tt_l1_ptr uint32_t* words = km::l1(to);
        const Served served = {words[kViewOn] != 0, words[kViewBase]};
        if (whole && served.on) {
            noc_async_read(region.get_noc_addr(1), to, kViewRegionBytes);
            if (!texel_pages::reads_arrived(mover)) {
                return {false, 0};
            }
        }
        return served;
    }

    // Mover A: two words handed to the pack CPU in the buffer `items` (false: gave
    // up).
    template <typename Reader_>
    bool hand(const Reader_& reader, uint32_t items, uint32_t first, uint32_t second) {
        if (!reader.reserve(items, 1)) {
            return false;
        }
        volatile tt_l1_ptr uint32_t* words = km::l1(get_write_ptr(items));
        words[0] = first;
        words[1] = second;
        cb_push_back(items, 1);
        return true;
    }

    // Mover A: item `id` (its planes at L1 `at`) handed on, then the pack CPU's asks
    // for it served until its end. False: gave up (recorded).
    template <typename Reader_>
    bool serve_item(
        const Reader_& reader,
        const km_command_t& command,
        uint32_t items,
        uint32_t id,
        uint32_t at,
        const texel_pages::AskBuffers& buffers,
        uint32_t base
    ) {
        if (!hand(reader, items, id, at)) {
            return false;
        }
        const InterleavedAddrGen<true> cube = {
            .bank_base_address = base, .page_size = kViewPageBytes
        };
        bool failed = false;
        const uint32_t code = reader.poll(
            [&] {
                const texel_pages::AskStep step = texel_pages::serve_ask(
                    reader, buffers, cube
                );
                failed = step == texel_pages::kAskFailed;
                return failed || step == texel_pages::kAskEnd;
            },
            reader.args().wait_limit
        );
        if (code == km::kGaveNone && !failed) {
            return true;
        }
        reader.gave_up(
            km::kStReader,
            failed ? km::kGaveBadItem : code,
            kWhereShowViewAsks,
            0,
            command.sequence
        );
        return false;
    }

    // Mover B: the pack CPU's token for the next item waited for and freed. False:
    // gave up (recorded by the wait).
    template <typename Writer_>
    bool viewed_wait(const Writer_& writer, uint32_t viewed) {
        if (!writer.wait_front(viewed, 1)) {
            return false;
        }
        cb_pop_front(viewed, 1);
        return true;
    }
#endif

}  // namespace show_view
