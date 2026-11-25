// The apply's mover A: the table pages to compute, its share of x's and the weights'
// streams, the head page to compute.
#pragma once

#include "apply.h"
#include "apply_window.hpp"

namespace apply_k {

    // The apply of one command on mover A. False: gave up (recorded).
    template <
        typename Mover,
        typename X,
        typename W,
        typename Y,
        typename Tables,
        typename Profile>
    inline bool apply_reader(
        const Mover& reader,
        const km_command_t& command,
        const X& x,
        const W& w,
        const Y& y,
        const Tables& tables,
        const Profile& profile
    ) {
        [[maybe_unused]] Windows windows;  // the frame program's places
        static_cast<void>(y);
        static_cast<void>(profile);
        const uint32_t rank = reader.me() - km::first(command);
        const uint32_t base = rank * kConstPages;
        for (uint32_t p = 0; p < kConstPages; p++) {
            if (!reader.reserve(kFieldTable, 1) ||
                !km::read_pages(
                    reader, command, tables, base + p, 1, get_write_ptr(kFieldTable)
                )) {
                return false;
            }
            noc_async_read_barrier();
            invalidate_l1_cache();
            const volatile tt_l1_ptr uint32_t* page = (km::l1(
                get_write_ptr(kFieldTable)
            ));
            cb_push_back(kFieldTable, 1);
            const uint32_t count = entries(page);
            for (uint32_t at = 0; at < count; at++) {
                const volatile tt_l1_ptr uint32_t* e = entry(page, at);
                const uint32_t src = e[kSrc];
                const uint32_t k = e[kK] < kConstKmax ? e[kK] : kConstKmax;
                KM_STREAM(
                    xs, km::kMoveRead, x, src, k, kConstKmax, 1, kPairXIn, kReadPattern
                );
                if (k == 0) {  // an empty block: compute takes it all the same
                    if (!reader.reserve(kPairXIn.mover_a, kConstKmax)) {
                        return false;
                    }
                    cb_push_back(kPairXIn.mover_a, kConstKmax);
                } else if (!km::move(reader, xs)) {
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
                if (!km::move(reader, vt)) {
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
                if (!km::move(reader, ut)) {
                    return false;
                }
            }
        }
        if (!reader.reserve(kFieldHead, 1) ||
            !km::read_pages(
                reader, command, tables, base, 1, get_write_ptr(kFieldHead)
            )) {
            return false;
        }
        noc_async_read_barrier();
        invalidate_l1_cache();
        cb_push_back(kFieldHead, 1);
        return true;
    }

}  // namespace apply_k
