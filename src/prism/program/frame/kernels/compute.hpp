// The handler `work` on the compute CPUs: the frame's page and each descriptor taken
// by unpack and handed to math and pack, then the thread run on all three (a tile's
// steps, a range's kind) until the end descriptor; then the kind's end.
#pragma once

#include <stdint.h>

#include "pack.hpp"

namespace prism_frame {

    // The generated program's parts on the compute CPUs.
    // Each false: a give-up already recorded, the command ends.
    bool tile_compute(ComputeContext& ctx, const Tile& tile);
    bool kind_compute(ComputeContext& ctx, uint32_t kind, const Range& range);
    bool kind_end_compute(ComputeContext& ctx, uint32_t kind);

#if defined(TRISC_UNPACK)
    // The front page of buffer `cb`, waited for: its L1 address; 0: gave up.
    inline uint32_t front_of(const compute_mail::Waits& waits, uint32_t cb) {
        const bool ready = compute_mail::timed(
            waits.stops,
            waits.cycles,
            [&] {
                const uint16_t received = (reg_read(
                    reinterpret_cast<uint32_t>(get_cb_tiles_received_ptr(cb))
                ));
                const uint16_t acked = get_local_cb_interface(cb).tiles_acked;
                return static_cast<uint16_t>(received - acked) >= 1;
            },
            waits.stops.where_front
        );
        if (!ready) {
            return 0;
        }
        cb_wait_front(cb, 1);
        return get_tile_l1_byte_address(cb, 0);
    }

    // `word` to math and pack.
    inline void to_both(uint32_t word) {
        ckernel::mailbox_write(ckernel::ThreadId::MathThreadId, word);
        ckernel::mailbox_write(ckernel::ThreadId::PackThreadId, word);
    }

    // A word of math and one of pack (each a confirmation). False: gave up.
    inline bool from_both(const compute_mail::Waits& waits) {
        for (const auto thread :
             {ckernel::ThreadId::MathThreadId, ckernel::ThreadId::PackThreadId}) {
            if (!waits.mail_from(thread)) {
                return false;
            }
            static_cast<void>(ckernel::mailbox_read(thread));
        }
        return true;
    }
#else
    // A word of unpack (0: unpack gave up).
    inline uint32_t from_unpack(const compute_mail::Waits& waits) {
        if (!waits.mail_from(ckernel::ThreadId::UnpackThreadId)) {
            return 0;
        }
        return ckernel::mailbox_read(ckernel::ThreadId::UnpackThreadId);
    }
#endif

    // The next descriptor into `d` on all three: unpack waits for it and hands its
    // address on; math and pack copy it and confirm; unpack frees it. False: gave up.
    inline bool take(const ComputeContext& ctx, uint32_t* d) {
        const compute_mail::Waits waits = waits_at(ctx, FW_C_MAIL);
        uint32_t at = 0;
#if defined(TRISC_UNPACK)
        at = front_of(waits_at(ctx, FW_C_DESCRIPTOR), kFieldFrameJobs);
        to_both(at);
#else
        at = from_unpack(waits);
#endif
        if (at == 0) {
            return false;
        }
        invalidate_l1_cache();
        const volatile uint32_t* from = reinterpret_cast<const volatile uint32_t*>(at);
        for (uint32_t word = 0; word < FD_WORDS; word++) {
            d[word] = from[word];
        }
#if defined(TRISC_UNPACK)
        if (!from_both(waits)) {
            return false;
        }
        cb_pop_front(kFieldFrameJobs, 1);
#else
        ckernel::mailbox_write(ckernel::ThreadId::UnpackThreadId, 1);
#endif
        return true;
    }

    // `work` on a compute CPU: the frame's page, the threads, the kind's end; unpack
    // frees the page once math and pack are done with it.
    inline void work_compute(km::Compute& compute, const km_command_t& command) {
        uint32_t page = 0, memory = 0;
        const compute_mail::Waits mail = {
            {compute.control(),
             km::kGaveLimit,
             km::kGaveBadItem,
             FW_C_MAIL,
             FW_C_MAIL,
             FW_BAD},
            FW_WAIT_CYCLES
        };
#if defined(TRISC_UNPACK)
        compute_mail::Waits at_page = mail;
        at_page.stops.where_front = FW_C_PAGE;
        page = front_of(at_page, kFieldFramePage);
        memory = get_local_cb_interface(kFieldFrameMemory).fifo_rd_ptr << 4;
        to_both(page);
        to_both(memory);
#else
        page = from_unpack(mail);
        memory = from_unpack(mail);
#endif
        if (page == 0) {
            return;
        }
        ComputeContext ctx = {
            compute,
            command,
            reinterpret_cast<const volatile uint32_t*>(page),
            memory,
            compute.me() - km::first(command),
            km::count(command),
            0,
            {},
            {0, 0}
        };
        for (;;) {
            uint32_t d[FD_WORDS];
            if (!take(ctx, d)) {
                return;
            }
            if (d[FD_KIND] == FD_END) {
                break;
            }
            if (d[FD_KIND] == TP_TILE) {
                if (!tile_compute(ctx, tile_of(d))) {
                    return;
                }
#if defined(TRISC_PACK)
                if (!thread_end(ctx)) {
                    return;
                }
#endif
                continue;
            }
            if (!kind_compute(ctx, d[FD_KIND], range_of(d))) {
                return;
            }
        }
        if (!kind_end_compute(ctx, ctx.word(TF_PULL))) {
            return;
        }
#if defined(TRISC_UNPACK)
        if (from_both(mail)) {
            cb_pop_front(kFieldFramePage, 1);
        }
#else
        ckernel::mailbox_write(ckernel::ThreadId::UnpackThreadId, 1);
#endif
    }

}  // namespace prism_frame
