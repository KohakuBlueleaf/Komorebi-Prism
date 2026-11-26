// The account of the handler `work` (frame.h FX_*): the command's counters in the
// handler's memory, written to the core's page by (view, pull), and a record a thread;
// every call nothing unless the build defines PRISM_FRAME_ACCOUNT 1.
#pragma once

#include <stdint.h>

#include "context.hpp"

#ifndef PRISM_FRAME_ACCOUNT
#define PRISM_FRAME_ACCOUNT 0
#endif

namespace prism_frame {

    constexpr bool kAccount = PRISM_FRAME_ACCOUNT != 0;

    // The account's words in the handler's memory at `memory`.
    inline volatile uint32_t* account_words(uint32_t memory) {
        return reinterpret_cast<volatile uint32_t*>(memory + kFrameAccountAt);
    }

    // The command's block: its first word.
    template <typename Ctx>
    inline volatile uint32_t* account_block(const Ctx& ctx) {
        return account_words(ctx.memory);
    }

    // The place of the command's (view, pull) block in a core's page, in words.
    template <typename Ctx>
    inline uint32_t account_page_block(const Ctx& ctx) {
        const uint32_t pull = ctx.word(TF_PULL);
        const uint32_t index = pull == TP_COUNT ? 0u : pull == TP_PLACE ? 1u : 2u;
        const uint32_t view = (ctx.word(TF_VIEW) & 0xFFu) % FX_VIEWS;
        return FX_PAGE_BLOCKS + (view * FX_ACCOUNT_PULLS + index) * FX_BLOCK_WORDS;
    }

    // A core's page of the account: its bytes.
    template <typename Ctx>
    inline uint32_t account_page_bytes(const Ctx& ctx) {
        return 4u * (FX_RECORDS_AT + FX_RECORD_WORDS * ctx.word(TF_ACCOUNT_RECORDS));
    }

    inline uint32_t account_now() {
        if constexpr (kAccount) {
            return km::wall();
        }
        return 0;
    }

    // Mover B, a compute CPU (1 + its index): its words of the command are written.
    template <typename Ctx>
    inline void account_done(const Ctx& ctx, uint32_t who) {
        if constexpr (kAccount) {
            account_words(ctx.memory)[FX_DONE_AT + who] = ctx.command.sequence;
        }
    }

#if !defined(COMPILE_FOR_TRISC)
    // This mover's words of the block.
    constexpr uint32_t kAccountMover = (
        km::kMover == km::kMoverA ? FX_MOVER_A : FX_MOVER_B
    );

    // Mover A at the command's start, before anything is handed on: the block zeroed.
    inline void account_begin(const MoverContext& ctx) {
        if constexpr (kAccount) {
            volatile uint32_t* block = account_block(ctx);
            for (uint32_t word = 0; word < FX_BLOCK_WORDS; word++) {
                block[word] = 0;
            }
        }
    }

    // Mover A: the records written since the load.
    inline uint32_t& account_records() {
        static uint32_t records = 0;
        return records;
    }

    // `value` added to this mover's word `word` of the command's block.
    inline void account_add(const MoverContext& ctx, uint32_t word, uint32_t value) {
        if constexpr (kAccount) {
            account_block(ctx)[kAccountMover + word] += value;
        }
    }

    // The cycles since `since` added to the block's word `word` (not a mover's).
    inline void account_word_since(
        const MoverContext& ctx, uint32_t word, uint32_t since
    ) {
        if constexpr (kAccount) {
            account_block(ctx)[word] += km::wall() - since;
        }
    }

    // The cycles since `since` added to this mover's word `word`.
    inline void account_since(const MoverContext& ctx, uint32_t word, uint32_t since) {
        if constexpr (kAccount) {
            account_block(ctx)[kAccountMover + word] += km::wall() - since;
        }
    }

    // Mover A: the ask and answer times of the thread at place `taken`, its step ends
    // cleared.
    inline void account_taken(
        const MoverContext& ctx, uint32_t taken, uint32_t asked, uint32_t answered
    ) {
        if constexpr (kAccount) {
            volatile uint32_t* at = account_words(ctx.memory) + FX_TAKEN_AT;
            at[2 * (taken % FM_RING)] = asked;
            at[2 * (taken % FM_RING) + 1] = answered;
            volatile uint32_t* steps = account_words(ctx.memory) + FX_STEPS_AT;
            for (uint32_t step = 0; step < FX_STEPS; step++) {
                steps[(taken % FM_RING) * FX_STEPS + step] = 0;
            }
        }
    }

    // Mover A: the record of the thread at place `at` (FM_RING) written to the core's
    // page of the account (none when the page word is 0).
    inline void account_record(
        const MoverContext& ctx,
        uint32_t at,
        uint32_t kind,
        uint32_t number,
        uint32_t start,
        uint32_t end_a,
        uint32_t end_b,
        uint32_t cost
    ) {
        if constexpr (kAccount) {
            const uint32_t base = ctx.word(TF_ACCOUNT);
            const uint32_t held = ctx.word(TF_ACCOUNT_RECORDS);
            if (base == 0 || held == 0) {
                return;
            }
            volatile uint32_t* words = account_words(ctx.memory);
            const uint32_t index = account_records();
            if (index % FM_RING == 0) {
                ctx.movement.wait(
                    [] {
                        return ncrisc_noc_nonposted_writes_flushed(noc_index);
                    },
                    FW_OUTPUT
                );
            }
            volatile uint32_t* r = (
                words + FX_STAGE_AT + (index % FM_RING) * FX_RECORD_WORDS
            );
            r[FX_R_VIEW] = (ctx.word(TF_VIEW) & 0xFFFFu) | kind << 16;
            r[FX_R_NUMBER] = number;
            r[FX_R_COUNT] = 0;
            r[FX_R_ASKED] = words[FX_TAKEN_AT + 2 * at];
            r[FX_R_TAKEN] = words[FX_TAKEN_AT + 2 * at + 1];
            r[FX_R_START] = start;
            r[FX_R_END_A] = end_a;
            r[FX_R_END_B] = end_b;
            r[FX_R_COST] = cost;
            for (uint32_t step = 0; step < FX_RECORD_WORDS - FX_R_STEPS; step++) {
                r[FX_R_STEPS + step] = (
                    kind == TP_TILE ? words[FX_STEPS_AT + at * FX_STEPS + step] : 0u
                );
            }
            const InterleavedAddrGen<true> pages = {
                .bank_base_address = base, .page_size = account_page_bytes(ctx)
            };
            const uint32_t offset = (
                4u * (FX_RECORDS_AT + FX_RECORD_WORDS * (index % held))
            );
            noc_async_write(
                reinterpret_cast<uint32_t>(r),
                pages.get_noc_addr(ctx.rank + km::first(ctx.command), offset),
                4u * FX_RECORD_WORDS
            );
            account_records() = index + 1;
        }
    }

    // Mover A: whether mover B and the compute CPUs wrote their words of the command.
    inline bool account_all_done(const MoverContext& ctx) {
        invalidate_l1_cache();
        volatile uint32_t* done = account_words(ctx.memory) + FX_DONE_AT;
        for (uint32_t who = 0; who < 4; who++) {
            if (done[who] != ctx.command.sequence) {
                return false;
            }
        }
        return true;
    }

    // Mover A at the command's end, once the others wrote theirs: the head and the
    // block to the core's page, waited for.
    inline void account_flush(const MoverContext& ctx) {
        if constexpr (kAccount) {
            const uint32_t base = ctx.word(TF_ACCOUNT);
            if (base == 0) {
                return;
            }
            ctx.movement.wait(
                [&] {
                    return account_all_done(ctx);
                },
                FW_DRAIN
            );
            volatile uint32_t* head = account_words(ctx.memory) + FX_HEAD_AT;
            head[0] = account_records();
            const InterleavedAddrGen<true> pages = {
                .bank_base_address = base, .page_size = account_page_bytes(ctx)
            };
            const uint32_t page = ctx.rank + km::first(ctx.command);
            noc_async_write(
                reinterpret_cast<uint32_t>(head),
                pages.get_noc_addr(page, 0),
                4u * FX_HEAD_WORDS
            );
            noc_async_write(
                reinterpret_cast<uint32_t>(account_block(ctx)),
                pages.get_noc_addr(page, 4u * account_page_block(ctx)),
                4u * FX_BLOCK_WORDS
            );
            ctx.movement.wait(
                [] {
                    return ncrisc_noc_nonposted_writes_flushed(noc_index);
                },
                FW_OUTPUT
            );
        }
    }
#else
    // A compute CPU's words of the command's block.
    template <typename Ctx>
    inline volatile uint32_t* account_cpu(const Ctx& ctx, uint32_t cpu) {
        return account_block(ctx) + FX_CPU_AT + cpu * FX_CPU_WORDS;
    }

    // `run()` (a step's or a kind's compute) timed as step `step` of compute CPU `cpu`;
    // on pack its end kept for the thread at place `sequence`. Its result.
    template <typename Ctx, typename Run>
    inline bool account_step(
        const Ctx& ctx, uint32_t cpu, uint32_t step, uint32_t sequence, Run run
    ) {
        if constexpr (kAccount) {
            const uint32_t since = km::wall();
            const bool ok = run();
            const uint32_t now = km::wall();
            account_cpu(ctx, cpu)[FX_CPU_STEP + step] += now - since;
            if (cpu == 2 && step < FX_STEPS) {
                const uint32_t at = FX_STEPS_AT + sequence % FM_RING * FX_STEPS + step;
                account_words(ctx.memory)[at] = now;
            }
            return ok;
        }
        return run();
    }

    // A thread of compute CPU `cpu` run since `since`.
    template <typename Ctx>
    inline void account_thread(const Ctx& ctx, uint32_t cpu, uint32_t since) {
        if constexpr (kAccount) {
            volatile uint32_t* words = account_cpu(ctx, cpu);
            words[0] += km::wall() - since;
            words[FX_CPU_THREADS] += 1;
        }
    }
#endif

}  // namespace prism_frame
