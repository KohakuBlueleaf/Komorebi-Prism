// The handler `work` on both movers: mover A copies the frame's page for compute, takes
// threads from its X280 core's pull and hands each to compute and to mover B; each
// mover runs its share of a thread's movement and serves its half at every wait.
#pragma once

#include <new>
#include <stdint.h>

#include "../../../core/include/grid.h"
#include "komorebi/device/core/km_x280.hpp"
#include "serve.hpp"

namespace prism_frame {

    // The generated program's parts on a mover: a range's movement by the pull's kind,
    // the kind's end, the layers a tile thread's list passes walk by the view.
    bool kind_movers(MoverContext& ctx, uint32_t kind, const Range& range);
    bool kind_end_movers(MoverContext& ctx, uint32_t kind);
    bool steps_begin(MoverContext& ctx);
    const uint32_t* stream_layers(uint32_t view, uint32_t& count);

    // The port, made once for the life of the kernel (mover A's).
    inline km::X280Port& port_of(const km::Movement& movement) {
        alignas(km::X280Port) static unsigned char store[sizeof(km::X280Port)];
        static bool made = false;
        if (!made) {
            new (store) km::X280Port(movement);
            made = true;
        }
        return *reinterpret_cast<km::X280Port*>(store);
    }

    // Mover A: the command's block copied into the frame's page ring for compute.
    inline bool publish_page(MoverContext& ctx, MoverState& state, uint32_t bytes) {
        if (!wait_serving(
                ctx,
                state,
                [] {
                    return cb_pages_reservable_at_back(kFieldFramePage, 1);
                },
                FW_PAGE
            )) {
            return false;
        }
        cb_reserve_back(kFieldFramePage, 1);
        volatile tt_l1_ptr uint32_t* to = km::l1(get_write_ptr(kFieldFramePage));
        for (uint32_t word = 0; word < TF_WORDS; word++) {
            to[word] = 4 * word < bytes ? ctx.page[word] : 0;
        }
        cb_push_back(kFieldFramePage, 1);
        return true;
    }

    // Mover A: a tile's record and its slice's words read; the record's slots made
    // absolute (its slice's place added) into the descriptor.
    inline bool read_record(MoverContext& ctx, uint32_t number, uint32_t* d) {
        const uint32_t record_at = ctx.memory + FM_RECORD_AT;
        const uint32_t slice_at = ctx.memory + FM_SLICE_AT;
        const InterleavedAddrGen<true> records = {
            .bank_base_address = ctx.word(TF_RECORDS), .page_size = TR_WORDS * 4
        };
        noc_async_read(records.get_noc_addr(number), record_at, TR_WORDS * 4);
        noc_async_read(
            get_noc_addr_from_bank_id<true>(
                ctx.bank, ctx.word(TF_SLICES) + TR_SLICE_OF(number) * TS_WORDS * 4
            ),
            slice_at,
            TS_WORDS * 4
        );
        if (!ctx.movement.wait(
                [] {
                    return ncrisc_noc_reads_flushed(noc_index);
                },
                FW_RECORD
            )) {
            return false;
        }
        account_add(ctx, FX_BYTES_RECORDS, (TR_WORDS + TS_WORDS) * 4);
        invalidate_l1_cache();
        volatile tt_l1_ptr uint32_t* record = km::l1(record_at);
        volatile tt_l1_ptr uint32_t* slice = km::l1(slice_at);
        for (uint32_t word = 0; word < TR_WORDS; word++) {
            d[FD_RECORD + word] = record[word];
        }
        for (uint32_t layer = 0; layer < TR_LAYERS; layer++) {
            d[FD_RECORD + TR_LAYER_SLOT(layer)] += slice[TS_PLACE(layer)];
        }
        return true;
    }

    // Mover A: a range's layer, first block and blocks from the layers' first ranges.
    inline bool decode_range(MoverContext& ctx, uint32_t number, uint32_t* d) {
        const uint32_t layers = ctx.word(TF_LAYER_COUNT);
        for (uint32_t layer = layers; layer-- > 0;) {
            const uint32_t first = ctx.layer(layer, TF_L_RANGE_FIRST);
            if (number < first) {
                continue;
            }
            const uint32_t block = (number - first) * ctx.word(TF_RANGE_BLOCKS);
            const uint32_t blocks = ctx.layer(layer, TF_L_BLOCKS);
            if (block >= blocks) {
                return ctx.gave_up(km::kGaveBadItem, FW_BAD);
            }
            const uint32_t left = blocks - block;
            d[FD_LAYER] = layer;
            d[FD_FIRST_BLOCK] = block;
            d[FD_BLOCKS] =
                (left < ctx.word(TF_RANGE_BLOCKS) ? left : ctx.word(TF_RANGE_BLOCKS));
            return true;
        }
        return ctx.gave_up(km::kGaveBadItem, FW_BAD);
    }

    // Mover A: a descriptor pushed into ring `cb` (room waited for, serving).
    inline bool push_descriptor(
        MoverContext& ctx, MoverState& state, uint32_t cb, const uint32_t* d
    ) {
        if (!wait_serving(
                ctx,
                state,
                [cb] {
                    return cb_pages_reservable_at_back(cb, 1);
                },
                FW_DESCRIPTOR_ROOM
            )) {
            return false;
        }
        cb_reserve_back(cb, 1);
        volatile tt_l1_ptr uint32_t* to = km::l1(get_write_ptr(cb));
        for (uint32_t word = 0; word < FD_WORDS; word++) {
            to[word] = d[word];
        }
        cb_push_back(cb, 1);
        return true;
    }

    // Mover B: the next descriptor of its ring (waited for, serving).
    inline bool take_descriptor(MoverContext& ctx, MoverState& state, uint32_t* d) {
        const uint32_t since = account_now();
        if (!wait_serving(
                ctx,
                state,
                [] {
                    return cb_pages_available_at_front(kFieldFrameJobsB, 1);
                },
                FW_DESCRIPTOR
            )) {
            return false;
        }
        account_since(ctx, FX_ASK, since);
        invalidate_l1_cache();
        volatile tt_l1_ptr uint32_t* from = km::l1(get_read_ptr(kFieldFrameJobsB));
        for (uint32_t word = 0; word < FD_WORDS; word++) {
            d[word] = from[word];
        }
        cb_pop_front(kFieldFrameJobsB, 1);
        return true;
    }

    // This mover's share of a tile thread's list passes: each layer of the view's
    // stream with entries, its pages in chunks, room for a chunk's blocks waited for
    // serving, so that no stream wait holds a request of this half.
    inline bool stream_lists(MoverContext& ctx, MoverState& state, const Tile& tile) {
        uint32_t count = 0;
        const uint32_t* layers = stream_layers(view_kind(ctx.page), count);
        for (uint32_t at = 0; at < count; at++) {
            const uint32_t layer = layers[at];
            const ListSpan span = span_of(tile.slot[layer], tile.entries[layer]);
            if (span.blocks == 0) {
                continue;
            }
            const InterleavedAddrGen<true> lists = {
                .bank_base_address = ctx.layer(layer, TF_L_LISTS),
                .page_size = kFrameListPageBytes
            };
            for (uint32_t chunk = 0; chunk < span.blocks; chunk += FL_CHUNK_BLOCKS) {
                const uint32_t blocks =
                    (span.blocks - chunk < FL_CHUNK_BLOCKS ? span.blocks - chunk
                                                           : FL_CHUNK_BLOCKS);
                uint32_t mine = 0;
                for (uint32_t block = 0; block < blocks; block++) {
                    mine += kListPattern.owner(block) == km::kMover;
                }
                if (mine == 0) {
                    continue;
                }
                const uint32_t half = kListPair.half(km::kMover);
                if (!wait_serving(
                        ctx,
                        state,
                        [half, mine] {
                            return (cb_pages_reservable_at_back(
                                half, mine * kFrameBlockPages
                            ));
                        },
                        FW_LIST_ROOM
                    )) {
                    return false;
                }
                const uint32_t first = chunk * kFrameBlockPages;
                const uint32_t left = span.pages - first;
                const uint32_t pages =
                    (left < blocks * kFrameBlockPages ? left
                                                      : blocks * kFrameBlockPages);
                km::Moved moved = {0, 0};
                const km::Stream stream(
                    km::kMoveRead,
                    lists,
                    span.first_page + first,
                    pages,
                    kFrameBlockPages,
                    1,
                    kListPair,
                    kListPattern
                );
                if (!ctx.movement.move(moved, stream)) {
                    return false;
                }
                account_add(ctx, FX_BYTES_LISTS, moved.tiles * kFrameListPageBytes);
            }
        }
        return true;
    }

    // This mover's share of a thread: a tile's list passes (its end comes with the
    // compute side's end ask), a range's movement (ended when it returns).
    inline bool run_share(MoverContext& ctx, MoverState& state, const uint32_t* d) {
        const uint32_t at = state.taken % FM_RING;
        state.kind[at] = d[FD_KIND];
        state.number[at] = d[FD_NUMBER];
        state.start[at] = km::wall();
        state.taken++;
        if (d[FD_KIND] == TP_TILE) {
            const bool ok = stream_lists(ctx, state, tile_of(d));
            account_since(ctx, FX_RUN, state.start[at]);
            return ok;
        }
        if (!kind_movers(ctx, d[FD_KIND], range_of(d))) {
            return false;
        }
        account_since(ctx, FX_RUN, state.start[at]);
        ended_here(ctx, state);
        return true;
    }

    // Mover A: threads ended on both movers.
    inline uint32_t ended(const MoverContext& ctx, const MoverState& state) {
        const uint32_t b = b_done(ctx);
        return state.done < b ? state.done : b;
    }

    // Mover A: the newest thread ended on both movers told with its cost.
    inline bool tell(MoverContext& ctx, MoverState& state, km::X280Port& port) {
        const uint32_t both = ended(ctx, state);
        if (both == state.told) {
            return true;
        }
        state.told = both;
        const uint32_t at = (both - 1) % FM_RING;
        invalidate_l1_cache();
        const uint32_t b_end = shared(ctx)[FM_B_ENDS + at];
        const uint32_t a_end = state.end[at];
        const uint32_t
            last = (b_end - state.start[at] > a_end - state.start[at] ? b_end : a_end);
        account_record(
            ctx,
            at,
            state.kind[at],
            state.number[at],
            state.start[at],
            a_end,
            b_end,
            (last - state.start[at]) >> TA_COST_SHIFT
        );
        return (port.tell(
            state.number[at], (last - state.start[at]) >> TA_COST_SHIFT, kFrameHeldCodes
        ));
    }

    // Mover A: threads from the pull until none is left, each handed on and its share
    // run; at most one taken ahead of the oldest not ended; then the end descriptor.
    inline bool take_threads(MoverContext& ctx, MoverState& state, uint32_t pull) {
        km::X280Port& port = port_of(ctx.movement);
        for (;;) {
            const uint32_t waited = account_now();
            if (!wait_serving(
                    ctx,
                    state,
                    [&] {
                        return state.taken - ended(ctx, state) <= 1;
                    },
                    FW_AHEAD
                )) {
                return false;
            }
            account_since(ctx, FX_AHEAD, waited);
            if (!tell(ctx, state, port)) {
                return false;
            }
            uint32_t first = 0, word = 0;
            const uint32_t asked = account_now();
            const uint32_t count = port.next(first, word);
            const uint32_t answered = account_now();
            account_add(ctx, count == 0 ? FX_NONE : FX_ASK, answered - asked);
            account_taken(ctx, state.taken, asked, answered);
            if (count == 0) {
                if (port.pull_gave_up()) {
                    return false;
                }
                break;
            }
            uint32_t d[FD_WORDS] = {};
            d[FD_KIND] = pull;
            d[FD_NUMBER] = first;
            d[FD_COUNT] = count;
            d[FD_WORD] = word;
            d[FD_SEQUENCE] = state.taken;
            const bool known =
                (pull == TP_TILE ? read_record(ctx, first, d)
                                 : decode_range(ctx, first, d));
            account_add(ctx, FX_THREADS, 1);
            if (!known || !push_descriptor(ctx, state, kFieldFrameJobs, d) ||
                !push_descriptor(ctx, state, kFieldFrameJobsB, d) ||
                !run_share(ctx, state, d)) {
                return false;
            }
        }
        uint32_t end[FD_WORDS] = {};
        end[FD_KIND] = FD_END;
        return (
            push_descriptor(ctx, state, kFieldFrameJobs, end) &&
            push_descriptor(ctx, state, kFieldFrameJobsB, end)
        );
    }

    // Mover B: descriptors until the end one, each thread's share run.
    inline bool follow_threads(MoverContext& ctx, MoverState& state) {
        for (;;) {
            uint32_t d[FD_WORDS];
            if (!take_descriptor(ctx, state, d)) {
                return false;
            }
            if (d[FD_KIND] == FD_END) {
                return true;
            }
            if (!run_share(ctx, state, d)) {
                return false;
            }
        }
    }

    // `work` on a mover: on mover A in a tile pull the steps' begin, then the frame's
    // page; the threads, every thread taken ended here, the kind's end.
    inline bool work_movement(km::Movement& movement, const km_command_t& command) {
        const km::Block block = movement.block(command);
        MoverContext ctx = {
            movement,
            command,
            block.words,
            get_write_ptr(kFieldCommandSpace) + PRISM_SPACE_FRAME_MEMORY_AT,
            block.words == nullptr ? 0u : bank_word(block.words[TF_GRID]) - 1u,
            movement.me() - km::first(command),
            km::count(command)
        };
        if (block.words == nullptr || bank_word(block.words[TF_GRID]) == 0) {
            return ctx.gave_up(km::kGaveBadItem, FW_BAD);
        }
        MoverState state;
        const uint32_t pull = ctx.word(TF_PULL);
        if (pull != TP_COUNT && pull != TP_PLACE && pull != TP_TILE) {
            return ctx.gave_up(km::kGaveBadItem, FW_BAD);
        }
        const uint32_t began = account_now();
        if constexpr (kMine) {
            account_begin(ctx);
            if ((pull == TP_TILE && !steps_begin(ctx)) ||
                !publish_page(ctx, state, block.bytes) ||
                !take_threads(ctx, state, pull)) {
                return false;
            }
        } else {
            b_begin(ctx);
            if (!follow_threads(ctx, state)) {
                return false;
            }
        }
        const uint32_t draining = account_now();
        if (!wait_serving(
                ctx,
                state,
                [&] {
                    return state.done == state.taken;
                },
                FW_DRAIN
            )) {
            return false;
        }
        if constexpr (kMine) {
            if (!wait_serving(
                    ctx,
                    state,
                    [&] {
                        return b_done(ctx) == state.taken;
                    },
                    FW_DRAIN
                ) ||
                !tell(ctx, state, port_of(movement))) {
                return false;
            }
        }
        account_since(ctx, FX_DRAIN, draining);
        const bool ended = kind_end_movers(ctx, pull);
        account_since(ctx, FX_SPAN, began);
        if constexpr (kMine) {
            account_flush(ctx);
        } else {
            account_done(ctx, 0);
        }
        return ended;
    }

}  // namespace prism_frame
