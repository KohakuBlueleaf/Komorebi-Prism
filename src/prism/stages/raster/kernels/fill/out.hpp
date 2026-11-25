// FILL's output pages on the pack thread: the timed reserve, the item's bound, the
// planes' rows out of Dst, the push once the stores have landed.
#pragma once

#include <stdint.h>

#include "../common/give_up.hpp"
#include "vector.hpp"

namespace fill_k {

    // Polls ready() for at most kWaitCycles. False: gave up (recorded at `where`).
    template <typename Ready>
    bool timed(uint32_t control, Ready ready, uint32_t where) {
        const uint32_t started = km::wall();
        while (!ready()) {
            if (km::wall() - started > kWaitCycles) {
                setup_k::give_up(control, kGaveWait, where);
                return false;
            }
        }
        return true;
    }

    inline uint32_t out_ptr(uint32_t out) {
        return get_local_cb_interface(out).fifo_wr_ptr << 4;
    }

    // An item of `pages` at `destination` must end inside the output buffer; otherwise
    // the give-up goes to the writer's gave-up word and the stop flag is set.
    inline bool item_fits(
        uint32_t control, uint32_t out, uint32_t destination, uint32_t pages
    ) {
        if (destination + pages * kOutPageBytes <=
            (get_local_cb_interface(out).fifo_limit << 4)) {
            return true;
        }
        setup_k::give_up(control, kGaveBadItem, kWhereBadOut);
        return false;
    }

    // Timed cb_reserve_back on the output buffer.
    inline bool reserve_out(uint32_t control, uint32_t out, uint32_t pages) {
        const bool reserved = timed(
            control,
            [&] {
                const uint16_t acked = (reg_read(
                    reinterpret_cast<uint32_t>(get_cb_tiles_acked_ptr(out))
                ));
                const uint16_t used = get_local_cb_interface(out).tiles_received -
                    acked;
                return get_local_cb_interface(out).fifo_num_pages - used >= pages;
            },
            kWhereWaitOut
        );
        if (reserved) {
            cb_reserve_back(out, pages);
        }
        return reserved;
    }

    // Stores to L1 finished (a load of the last word written, address + 4 (words - 1),
    // used), then pushed.
    inline void push_out(
        uint32_t out, uint32_t address, uint32_t words, uint32_t pages
    ) {
        asm volatile("fence" ::: "memory");
        const uint32_t last_word = (reinterpret_cast<volatile uint32_t*>(
            address
        )[words - 1]);
        asm volatile("and x0, x0, %0" : : "r"(last_word) : "memory");
        cb_push_back(out, pages);
    }

    // Dst words [first_word, first_word + words) to L1 at `destination`.
    inline void copy_out(uint32_t destination, uint32_t first_word, uint32_t words) {
        km::dst::read(
            reinterpret_cast<volatile uint32_t*>(destination), first_word, words
        );
    }

    // Rows [first_row, end_row) of each plane to the same place in the item at
    // `destination`; without the window whole planes (the writer sends the band's).
    inline void copy_band(uint32_t destination, uint32_t first_row, uint32_t end_row) {
#if KM_DST_WINDOW
        const uint32_t first_word = kRowBytes / 4 * first_row;
        const uint32_t words = kRowBytes / 4 * (end_row - first_row);
        for (uint32_t plane = 0; plane < kPlanes; ++plane) {
            copy_out(
                destination + 4 * (plane * kPlaneWords + first_word),
                plane * kPlaneWords + first_word,
                words
            );
        }
#else
        fill::packing(true);
        copy_out(destination, 0, kPlanes * kPlaneWords);
        fill::packing(false);
#endif
    }

}  // namespace fill_k
