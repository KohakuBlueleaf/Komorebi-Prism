// The pack CPU's side of the handler `work` for the steps that run in it: asks of the
// movers' request rings (in turn), waits for an ask served, output blocks pushed into
// the half whose turn it is, and the thread's end told to both movers.
#pragma once

#include <stdint.h>

#include "../../../core/include/compute_mail.hpp"
#include "context.hpp"

namespace prism_frame {

    // A compute CPU's waits at `where`: the limit FW_WAIT_CYCLES, a bad item at FW_BAD.
    inline compute_mail::Waits waits_at(const ComputeContext& ctx, uint32_t where) {
        return {
            {ctx.compute.control(),
             km::kGaveLimit,
             km::kGaveBadItem,
             where,
             where,
             FW_BAD},
            FW_WAIT_CYCLES
        };
    }

#if defined(TRISC_PACK)
    constexpr uint32_t kAskRings[2] = {kFieldFrameAsksA, kFieldFrameAsksB};
    constexpr uint32_t kDoneRings[2] = {kFieldFrameDonesA, kFieldFrameDonesB};

    // An ask begun in the request ring whose turn it is, of pages of `page_bytes` of
    // the tensor at bank address `base`: its L1 address (0: gave up).
    inline uint32_t ask_begin(ComputeContext& ctx, uint32_t base, uint32_t page_bytes) {
        const uint32_t ring = kAskRings[ctx.ask_turn];
        if (!compute_mail::reserve(waits_at(ctx, FW_C_ASK), ring, 1)) {
            return 0;
        }
        const uint32_t ask = compute_mail::write_ptr(ring);
        volatile uint32_t* words = reinterpret_cast<volatile uint32_t*>(ask);
        words[FA_COUNT] = 0;
        words[FA_BASE] = base;
        words[FA_PAGE_BYTES] = page_bytes;
        words[FA_OUTPUTS] = 0;
        return ask;
    }

    // Entry `index` (below FA_ENTRIES) of the ask at `ask`: page `page` into L1 `to`.
    inline void ask_entry(uint32_t ask, uint32_t index, uint32_t page, uint32_t to) {
        volatile uint32_t* entry = reinterpret_cast<volatile uint32_t*>(ask) +
                                   FA_ENTRY_AT + FA_ENTRY_WORDS * index;
        entry[0] = page;
        entry[1] = to;
    }

    // The ask at `ask` of `count` entries pushed: the half that serves it (0 mover A,
    // 1 mover B), whose done ask_wait takes; the turn passes.
    inline uint32_t ask_post(ComputeContext& ctx, uint32_t ask, uint32_t count) {
        const uint32_t half = ctx.ask_turn;
        reinterpret_cast<volatile uint32_t*>(ask)[FA_COUNT] = count;
        compute_mail::push(kAskRings[half], ask + 4 * FA_COUNT, 1);
        ctx.ask_turn ^= 1u;
        return half;
    }

    // The next ask of half `half` served (its pages in L1), by the unpack CPU's
    // service of pack's mails (compute_mail::serve_mails). False: gave up.
    inline bool ask_wait(ComputeContext& ctx, uint32_t half) {
        const compute_mail::Waits waits = waits_at(ctx, FW_C_DONE);
        return compute_mail::front(waits, kDoneRings[half], 1) != 0 &&
               compute_mail::pop(waits, kDoneRings[half], 1);
    }

    // An output block of output `output` reserved in the half whose turn it is: its L1
    // address (the payload from FO_HEADER_BYTES on); 0: gave up.
    inline uint32_t out_reserve(ComputeContext& ctx, uint32_t output) {
        const uint32_t half = kFrameOutPairs[output].half(ctx.out_turn[output]);
        if (!compute_mail::reserve(waits_at(ctx, FW_C_OUT), half, 1)) {
            return 0;
        }
        return compute_mail::write_ptr(half);
    }

    // The block at `block` of output `output` pushed: `bytes` of its payload to page
    // `page` (pages of `page_bytes`) of the frame page's target from byte `offset`.
    inline void out_push(
        ComputeContext& ctx,
        uint32_t output,
        uint32_t block,
        uint32_t page,
        uint32_t offset,
        uint32_t bytes,
        uint32_t page_bytes
    ) {
        const uint32_t turn = ctx.out_turn[output];
        volatile uint32_t* header = reinterpret_cast<volatile uint32_t*>(block);
        header[FO_PAGE] = page;
        header[FO_OFFSET] = offset;
        header[FO_BYTES] = bytes;
        header[FO_PAGE_BYTES] = page_bytes;
        compute_mail::push(kFrameOutPairs[output].half(turn), block + 4 * FO_BYTES, 1);
        ctx.out_blocks[turn]++;
        ctx.out_turn[output] = turn ^ 1u;
    }

    // The thread's end told to both movers (each its output blocks); the counts
    // start again. False: gave up.
    inline bool thread_end(ComputeContext& ctx) {
        for (uint32_t half = 0; half < 2; half++) {
            const uint32_t ring = kAskRings[half];
            if (!compute_mail::reserve(waits_at(ctx, FW_C_ASK), ring, 1)) {
                return false;
            }
            const uint32_t ask = compute_mail::write_ptr(ring);
            volatile uint32_t* words = reinterpret_cast<volatile uint32_t*>(ask);
            words[FA_OUTPUTS] = ctx.out_blocks[half];
            words[FA_COUNT] = FA_THREAD_END;
            compute_mail::push(ring, ask + 4 * FA_COUNT, 1);
            ctx.out_blocks[half] = 0;
        }
        return true;
    }
#endif

}  // namespace prism_frame
