// A compute thread's waits on buffers when the pack CPU works alone (SHADE, LIGHT, any
// such stage): the pack thread's mails, the unpack thread's service, timed waits.
#pragma once

#include <stdint.h>

#include "ckernel.h"
#include "komorebi/device/km_worker.hpp"

namespace compute_mail {

    // Where a give-up goes: the core's control block, the codes and the places of a
    // wait for a mail, for a buffer, and of a bad item or table.
    struct Stops {
        uint32_t control;
        uint32_t gave_wait;
        uint32_t gave_bad;
        uint32_t where_mail;
        uint32_t where_front;
        uint32_t where_bad;
    };

    // The give-up in the writer's gave-up word (the first one is kept) and the stop.
    inline void stop(const Stops& stops, uint32_t code, uint32_t where) {
        volatile uint32_t* state = reinterpret_cast<volatile uint32_t*>(
            stops.control + KM_CONTROL_STATE
        );
        if (state[km::kStWriter] == 0) {
            state[km::kStWriter] = code | where << 8;
        }
        *reinterpret_cast<volatile uint32_t*>(stops.control + KM_CONTROL_STOP) = 1;
    }

    // Polls ready() for at most `cycles`. False: gave up (recorded at `where`).
    template <typename Ready>
    bool timed(const Stops& stops, uint32_t cycles, Ready ready, uint32_t where) {
        const uint32_t started = km::wall();
        while (!ready()) {
            if (km::wall() - started > cycles) {
                stop(stops, stops.gave_wait, where);
                return false;
            }
        }
        return true;
    }

    // The unpack thread's answers to the pack thread's mails: the front page of a
    // buffer (its address; 0: gave up), a pop (1), the end (no answer).
    constexpr uint32_t kOpFront = 1;
    constexpr uint32_t kOpPop = 2;
    constexpr uint32_t kOpEnd = 3;

    constexpr uint32_t mail(uint32_t op, uint32_t cb, uint32_t pages) {
        return cb | pages << 8 | op << 16;
    }

    // A compute thread's waits: their stops and their limit in cycles.
    struct Waits {
        Stops stops;
        uint32_t cycles;

        bool mail_from(ckernel::ThreadId thread) const {
            return timed(
                stops,
                cycles,
                [&] {
                    return ckernel::mailbox_not_empty(thread);
                },
                stops.where_mail
            );
        }
    };

#ifdef TRISC_UNPACK
    // Serves the pack thread's mails until its end (or a wait gives up).
    inline void serve_mails(const Waits& waits) {
        for (;;) {
            if (!waits.mail_from(ckernel::ThreadId::PackThreadId)) {
                return;
            }
            const uint32_t request = ckernel::mailbox_read(
                ckernel::ThreadId::PackThreadId
            );
            const uint32_t op = request >> 16, cb = request & 0xFF;
            const uint32_t pages = request >> 8 & 0xFF;
            if (op == kOpPop) {
                cb_pop_front(cb, pages);
                ckernel::mailbox_write(ckernel::ThreadId::PackThreadId, 1);
                continue;
            }
            if (op != kOpFront) {
                return;
            }
            const bool ready = timed(
                waits.stops,
                waits.cycles,
                [&] {
                    const uint16_t received = (reg_read(
                        reinterpret_cast<uint32_t>(get_cb_tiles_received_ptr(cb))
                    ));
                    const uint16_t acked = get_local_cb_interface(cb).tiles_acked;
                    return static_cast<uint16_t>(received - acked) >= pages;
                },
                waits.stops.where_front
            );
            if (!ready) {
                ckernel::mailbox_write(ckernel::ThreadId::PackThreadId, 0);
                return;
            }
            cb_wait_front(cb, pages);
            ckernel::mailbox_write(
                ckernel::ThreadId::PackThreadId, get_tile_l1_byte_address(cb, 0)
            );
        }
    }
#endif

#ifdef TRISC_PACK
    // The front `pages` of buffer `cb` (its L1 address; 0: gave up), by the unpack
    // thread.
    inline uint32_t front(const Waits& waits, uint32_t cb, uint32_t pages) {
        ckernel::mailbox_write(
            ckernel::ThreadId::UnpackThreadId, mail(kOpFront, cb, pages)
        );
        if (!waits.mail_from(ckernel::ThreadId::UnpackThreadId)) {
            return 0;
        }
        const uint32_t address = ckernel::mailbox_read(
            ckernel::ThreadId::UnpackThreadId
        );
        asm volatile("fence" ::: "memory");
        return address;
    }

    // The front `pages` of buffer `cb` freed, by the unpack thread.
    inline bool pop(const Waits& waits, uint32_t cb, uint32_t pages) {
        ckernel::mailbox_write(
            ckernel::ThreadId::UnpackThreadId, mail(kOpPop, cb, pages)
        );
        if (!waits.mail_from(ckernel::ThreadId::UnpackThreadId)) {
            return false;
        }
        (void)ckernel::mailbox_read(ckernel::ThreadId::UnpackThreadId);
        return true;
    }

    // The unpack thread's end.
    inline void end_mails() {
        ckernel::mailbox_write(ckernel::ThreadId::UnpackThreadId, mail(kOpEnd, 0, 0));
    }

    // Timed cb_reserve_back of `pages` on a buffer the pack thread fills.
    inline bool reserve(const Waits& waits, uint32_t cb, uint32_t pages) {
        const bool reserved = timed(
            waits.stops,
            waits.cycles,
            [&] {
                const uint16_t acked = (reg_read(
                    reinterpret_cast<uint32_t>(get_cb_tiles_acked_ptr(cb))
                ));
                const uint16_t used = get_local_cb_interface(cb).tiles_received - acked;
                return get_local_cb_interface(cb).fifo_num_pages - used >= pages;
            },
            waits.stops.where_front
        );
        if (reserved) {
            cb_reserve_back(cb, pages);
        }
        return reserved;
    }

    inline uint32_t write_ptr(uint32_t cb) {
        return get_local_cb_interface(cb).fifo_wr_ptr << 4;
    }

    // Stores to L1 done (a load of the last word, used), then pushed.
    inline void push(uint32_t cb, uint32_t last_address, uint32_t pages) {
        asm volatile("fence" ::: "memory");
        const uint32_t last_word = *reinterpret_cast<volatile uint32_t*>(last_address);
        asm volatile("and x0, x0, %0" : : "r"(last_word) : "memory");
        cb_push_back(cb, pages);
    }
#endif

}  // namespace compute_mail
