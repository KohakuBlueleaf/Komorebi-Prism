// A mover's service in the handler `work`: the compute side's asks of its half (pages
// read into L1, a thread's end), its halves of the output blocks (converted, written),
// and the threads it took that ended. Every wait of a mover serves.
#pragma once

#include <stdint.h>

#include "account.hpp"
#include "context.hpp"

namespace prism_frame {

    // A mover's threads in the command: taken, ended here, the thread-end asks seen;
    // the output blocks written and owed (both counted from the command's start);
    // a thread's kind, owed blocks, start and end by its place (FM_RING a ring).
    struct MoverState {
        uint32_t taken = 0, done = 0, ends = 0;
        uint32_t written = 0, owed_total = 0;
        uint32_t told = 0;
        uint32_t kind[FM_RING] = {};
        uint32_t owed[FM_RING] = {};
        uint32_t number[FM_RING] = {};
        uint32_t start[FM_RING] = {};
        uint32_t end[FM_RING] = {};
    };

    // This mover's halves.
    constexpr bool kMine = km::kMover == km::kMoverA;
    constexpr uint32_t kAsks = kMine ? kFieldFrameAsksA : kFieldFrameAsksB;
    constexpr uint32_t kDones = kMine ? kFieldFrameDonesA : kFieldFrameDonesB;

    // The generated program's halves of the output blocks, each drained (1: a block
    // written, 0: none, -1: gave up).
    int serve_outputs(MoverContext& ctx, MoverState& state);

    inline volatile tt_l1_ptr uint32_t* shared(const MoverContext& ctx) {
        return km::l1(ctx.memory);
    }

    // Mover B's threads ended, for mover A (0 while mover B is in another command).
    inline uint32_t b_done(const MoverContext& ctx) {
        invalidate_l1_cache();
        volatile tt_l1_ptr uint32_t* line = shared(ctx);
        if (line[FM_B_SEQUENCE] != ctx.command.sequence) {
            return 0;
        }
        return line[FM_B_DONE];
    }

    // Mover B's line made its own at the command's start.
    inline void b_begin(const MoverContext& ctx) {
        volatile tt_l1_ptr uint32_t* line = shared(ctx);
        line[FM_B_DONE] = 0;
        line[FM_B_SEQUENCE] = ctx.command.sequence;
    }

    // The next thread ended here: its end time, and mover B's line.
    inline void ended_here(const MoverContext& ctx, MoverState& state) {
        const uint32_t at = state.done % FM_RING;
        state.end[at] = km::wall();
        state.done++;
        if constexpr (!kMine) {
            volatile tt_l1_ptr uint32_t* line = shared(ctx);
            line[FM_B_ENDS + at] = state.end[at];
            line[FM_B_DONE] = state.done;
        }
    }

    // Tile threads whose end ask came and whose output blocks here are written.
    inline void advance(const MoverContext& ctx, MoverState& state) {
        while (state.done < state.taken && state.done < state.ends) {
            const uint32_t at = state.done % FM_RING;
            if (state.kind[at] != TP_TILE || state.written < state.owed[at]) {
                return;
            }
            ended_here(ctx, state);
        }
    }

    // One ask of this mover's request ring served: 1 served, 0 none or no room to
    // answer, -1 gave up.
    inline int serve_ask(MoverContext& ctx, MoverState& state) {
        if (!cb_pages_available_at_front(kAsks, 1)) {
            return 0;
        }
        invalidate_l1_cache();
        volatile tt_l1_ptr uint32_t* ask = km::l1(get_read_ptr(kAsks));
        const uint32_t count = ask[FA_COUNT];
        if (count == FA_THREAD_END) {
            state.owed_total += ask[FA_OUTPUTS];
            state.owed[state.ends % FM_RING] = state.owed_total;
            state.ends++;
            cb_pop_front(kAsks, 1);
            return 1;
        }
        if (count > FA_ENTRIES || ask[FA_PAGE_BYTES] == 0) {
            ctx.gave_up(km::kGaveBadItem, FW_BAD);
            return -1;
        }
        if (!cb_pages_reservable_at_back(kDones, 1)) {
            return 0;
        }
        const InterleavedAddrGen<true> pages = {
            .bank_base_address = ask[FA_BASE], .page_size = ask[FA_PAGE_BYTES]
        };
        for (uint32_t entry = 0; entry < count; entry++) {
            volatile tt_l1_ptr uint32_t*
                one = (ask + FA_ENTRY_AT + FA_ENTRY_WORDS * entry);
            noc_async_read(pages.get_noc_addr(one[0]), one[1], ask[FA_PAGE_BYTES]);
        }
        const bool landed = ctx.movement.wait(
            [] {
                return ncrisc_noc_reads_flushed(noc_index);
            },
            FW_REQUEST
        );
        if (!landed) {
            return -1;
        }
        account_add(ctx, FX_BYTES_ASKED, count * ask[FA_PAGE_BYTES]);
        cb_pop_front(kAsks, 1);
        cb_reserve_back(kDones, 1);
        cb_push_back(kDones, 1);
        return 1;
    }

    // One output block of this mover's half `half` written: `convert(ctx, payload,
    // bytes)` gives the bytes to write (in place); 1 written, 0 none, -1 gave up.
    template <typename Convert>
    inline int drain_output(
        MoverContext& ctx, MoverState& state, uint32_t half, Convert convert
    ) {
        if (!cb_pages_available_at_front(half, 1)) {
            return 0;
        }
        invalidate_l1_cache();
        const uint32_t block = get_read_ptr(half);
        volatile tt_l1_ptr uint32_t* header = km::l1(block);
        const uint32_t payload = block + FO_HEADER_BYTES;
        const uint32_t bytes = convert(ctx, payload, header[FO_BYTES]);
        if (bytes != 0) {
            const InterleavedAddrGen<true> target = {
                .bank_base_address = ctx.word(TF_TARGET),
                .page_size = header[FO_PAGE_BYTES]
            };
            noc_async_write(
                payload, target.get_noc_addr(header[FO_PAGE], header[FO_OFFSET]), bytes
            );
            const bool left = ctx.movement.wait(
                [] {
                    return ncrisc_noc_nonposted_writes_flushed(noc_index);
                },
                FW_OUTPUT
            );
            if (!left) {
                return -1;
            }
            account_add(ctx, FX_BYTES_OUT, bytes);
        }
        cb_pop_front(half, 1);
        state.written++;
        return 1;
    }

    // An output block written as it is.
    inline uint32_t as_it_is(MoverContext&, uint32_t, uint32_t bytes) {
        return bytes;
    }

    // One pass of the service: asks, output blocks, ended threads. -1: gave up.
    inline int serve(MoverContext& ctx, MoverState& state) {
        const uint32_t since = account_now();
        const int asked = serve_ask(ctx, state);
        if (asked < 0) {
            return -1;
        }
        const int drained = serve_outputs(ctx, state);
        if (drained < 0) {
            return -1;
        }
        advance(ctx, state);
        if (asked + drained > 0) {
            account_since(ctx, FX_SERVE, since);
        }
        return asked + drained > 0 ? 1 : 0;
    }

    // Waits for `ready()` at `where`, serving meanwhile. False: gave up (recorded).
    template <typename Ready>
    inline bool wait_serving(
        MoverContext& ctx, MoverState& state, Ready ready, uint32_t where
    ) {
        bool failed = false;
        const bool ok = ctx.movement.wait(
            [&] {
                if (serve(ctx, state) < 0) {
                    failed = true;
                    return true;
                }
                return ready();
            },
            where
        );
        return ok && !failed;
    }

}  // namespace prism_frame
