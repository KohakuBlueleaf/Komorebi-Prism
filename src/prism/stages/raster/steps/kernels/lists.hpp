// A layer's list on the compute CPUs as the loop's list pass streams it: block k of the
// layer's stream (kFrameBlockPages list pages, the last one shorter) in the half
// km::block_half(kListPair, kListPattern, k) its mover filled, taken in order; the pack
// CPU reads the tile's slots of it, the unpack CPU waits for it and hands it on, every
// compute CPU pops it.
#pragma once

#include <stdint.h>

#include "../../../../program/frame/kernels/context.hpp"
#include "../../kernels/common/layouts.hpp"
#include "komorebi/device/km_worker.hpp"

namespace list_step {

    using fill_k::kSlotsPerPage;
    using fill_k::kSlotWords;

    // One layer's slots [first, first + entries) of a pass, block by block: next() on
    // the pack CPU, run() on the others.
    template <typename Ctx>
    struct ListStream {
        const Ctx& ctx;
        prism_frame::ListSpan span;
        uint32_t slot = 0, end = 0;  // the next slot, the layer's end
        uint32_t block = 0, half = 0, pages = 0;
        uint32_t block_slot = 0, block_end = 0;  // the slots the block in hand holds
        uint32_t page = 0;  // the pack CPU's block in hand (0: none)
        bool failed = false;  // a wait gave up: the walk is over

        ListStream(const Ctx& of, uint32_t first, uint32_t entries) :
            ctx(of),
            span(prism_frame::span_of(first, entries)),
            slot(first),
            end(first + entries) {
        }

        // Block `block`'s pages, its half, its first slot; false: its wait gave up.
        bool acquire() {
            const uint32_t left = span.pages - block * kFrameBlockPages;
            pages = left < kFrameBlockPages ? left : kFrameBlockPages;
            half = km::block_half(
                prism_frame::kListPair, prism_frame::kListPattern, block
            );
            block_slot = (span.first_page + block * kFrameBlockPages) * kSlotsPerPage;
            block_end = block_slot + pages * kSlotsPerPage;
            if (!ctx.compute.wait_front(half, pages)) {
                failed = true;
                return false;
            }
            return true;
        }

        // The pack CPU's next slot of the layer; nullptr at its end or when a wait
        // gave up (end_walk() tells them apart).
        const volatile uint32_t* next() {
            if (failed || slot == end) {
                return nullptr;
            }
            if (page == 0 || slot >= block_end) {
                release();
                if (!acquire()) {
                    return nullptr;
                }
#if defined(TRISC_PACK)
                page = ctx.compute.handed(ckernel::ThreadId::UnpackThreadId);
                asm volatile("fence" ::: "memory");
#endif
            }
            const uint32_t at = slot++ - block_slot;
            return reinterpret_cast<const volatile uint32_t*>(page) + kSlotWords * at;
        }

        // The pack CPU's block given back and popped.
        void release() {
            if (page == 0) {
                return;
            }
#if defined(TRISC_PACK)
            ctx.compute.hand(ckernel::ThreadId::UnpackThreadId, 1);
#endif
            cb_pop_front(half, pages);
            page = 0;
            ++block;
        }

        // The pack CPU's walk ended: its last block given back; false when slots were
        // left (a wait gave up).
        bool end_walk() {
            release();
            return !failed && slot == end;
        }

        // The unpack and math CPUs: every block of the layer waited for; unpack hands
        // each to the pack CPU and pops it once the pack CPU gave it back. False: a
        // wait gave up.
        bool run() {
            for (block = 0; block < span.blocks; ++block) {
                if (!acquire()) {
                    return false;
                }
#if defined(TRISC_UNPACK)
                ctx.compute.hand(
                    ckernel::ThreadId::PackThreadId,
                    ckernel::get_tile_l1_byte_address(half, 0)
                );
                static_cast<void>(ctx.compute.handed(ckernel::ThreadId::PackThreadId));
#endif
                cb_pop_front(half, pages);
            }
            return true;
        }
    };

    // The pack CPU: the slots `list` has left taken and its blocks given back (none
    // when its walk ended). False: a wait gave up.
    template <typename Ctx>
    bool drain_rest(ListStream<Ctx>& list) {
        while (list.next() != nullptr) {
        }
        return list.end_walk();
    }

}  // namespace list_step
