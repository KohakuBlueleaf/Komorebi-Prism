// The apply's mover B: its own copy of the table pages, its share of the read streams,
// y's tiles and the profile page written.
#pragma once

#include "apply.h"
#include "apply_window.hpp"

namespace apply_k {

    // The apply of one command on mover B. False: gave up (recorded).
    template <
        typename Mover,
        typename X,
        typename W,
        typename Y,
        typename Tables,
        typename Profile>
    inline bool apply_writer(
        const Mover& writer,
        const km_command_t& command,
        const X& x,
        const W& w,
        const Y& y,
        const Tables& tables,
        const Profile& profile
    ) {
        [[maybe_unused]] Windows windows;  // the frame program's places
        const uint32_t rank = writer.me() - km::first(command);
        const uint32_t base = rank * kConstPages;
        for (uint32_t p = 0; p < kConstPages; p++) {
            if (!km::read_pages(
                    writer, command, tables, base + p, 1, get_write_ptr(kTableB)
                )) {
                return false;
            }
            noc_async_read_barrier();
            invalidate_l1_cache();
            const volatile tt_l1_ptr uint32_t* page = (km::l1(get_write_ptr(kTableB)));
            const uint32_t count = entries(page);
            for (uint32_t at = 0; at < count; at++) {
                const volatile tt_l1_ptr uint32_t* e = entry(page, at);
                const uint32_t src = e[kSrc];
                const uint32_t k = e[kK] < kConstKmax ? e[kK] : kConstKmax;
                KM_STREAM(
                    xs, km::kMoveRead, x, src, k, kConstKmax, 1, kPairXIn, kReadPattern
                );
                if (k != 0 && !km::move(writer, xs)) {
                    return false;
                }
                KM_STREAM(
                    vt,
                    km::kMoveRead,
                    w,
                    e[kW],
                    e[kA],
                    kConstBlock,
                    1,
                    kPairWIn,
                    kReadPattern
                );
                if (!km::move(writer, vt)) {
                    return false;
                }
                // the same stream armed again: the entry's U^T pages after its V's
                KM_STREAM(
                    ut,
                    km::kMoveRead,
                    w,
                    e[kU],
                    e[kB],
                    kConstBlock,
                    1,
                    kPairWIn,
                    kReadPattern
                );
                if (!km::move(writer, ut)) {
                    return false;
                }
            }
        }
        if (!km::read_pages(writer, command, tables, base, 1, get_write_ptr(kHeadB))) {
            return false;
        }
        noc_async_read_barrier();
        invalidate_l1_cache();
        const volatile tt_l1_ptr uint32_t* head = km::l1(get_write_ptr(kHeadB));
        const uint32_t first = head[kHeadFirst];
        const uint32_t own = head[kHeadOwn] < kConstOwn ? head[kHeadOwn] : kConstOwn;
        // y's tiles and the profile page as pack fills them, each written and popped
        for (uint32_t j = 0; j < own; j++) {
            if (!writer.wait_front(kFieldYPage, 1) ||
                !km::write_pages(
                    writer, command, y, first + j, 1, get_read_ptr(kFieldYPage)
                )) {
                return false;
            }
            noc_async_writes_flushed();
            cb_pop_front(kFieldYPage, 1);
        }
        if (!writer.wait_front(kFieldApplyProfile, 1) ||
            !km::write_pages(
                writer, command, profile, rank, 1, get_read_ptr(kFieldApplyProfile)
            )) {
            return false;
        }
        noc_async_write_barrier();
        cb_pop_front(kFieldApplyProfile, 1);
        return true;
    }

}  // namespace apply_k
