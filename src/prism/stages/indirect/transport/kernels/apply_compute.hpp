// The apply's compute: each entry's products summed onto the own sums in L1, the sums
// turned back into y's pages, the command's stamps.
#pragma once

#include "api/compute/matmul.h"
#include "api/compute/pack.h"
#include "api/compute/reconfig_data_format.h"
#include "api/compute/reg_api.h"
#include "api/compute/tile_move_copy.h"
#include "api/compute/transpose_dest.h"

#include "apply.h"
#include "apply_window.hpp"

namespace apply_k {

    // Each CPU's place in the entry's stream: the tile in the column, the column, the
    // product's set-up (0 none, 1 x read transposed, 2 t read as it is).
    struct Place {
        uint32_t tile = 0;
        uint32_t column = 0;
        uint32_t setup = 0;
    };

    inline Place place;
    // Pack's bit j: own sums tile j written this command.
    inline uint32_t touched[kOwnWords];
    // This CPU's wall clock at the handler's start, and its cycles inside the steps
    // below this command.
    inline uint32_t started = 0;
    inline uint32_t busy = 0;

    // A step's cycles, added to busy when it returns.
    struct Busy {
        uint32_t from = km::wall();

        ~Busy() {
            busy += km::wall() - from;
        }
    };

    // At the handler's start: no sum written yet; the products' set-up made again.
    inline void begin() {
        for (uint32_t i = 0; i < kOwnWords; i++) {
            touched[i] = 0;
        }
        place = Place{};
        busy = 0;
        started = km::wall();
    }

    // The set-up for products of `weights` (in0) by `vector` (in1, transposed or not).
    inline void setup(uint32_t weights, uint32_t vector, uint32_t form) {
        if (place.setup != form) {
            reconfig_data_format(vector, weights);
            matmul_block_init(weights, vector, form == 1 ? 1 : 0, 1, 1, 1);
            place.setup = form;
        }
    }

    // The packer set for buffer `cb`, its formats and shape named at compile time.
    template <uint32_t cb>
    inline void pack_format() {
#if defined(TRISC_PACK)
        constexpr uint32_t src = pack_src_format[cb];
        constexpr uint32_t dst = pack_dst_format[cb];
        constexpr uint32_t c_dim = pack_tile_c_dim[cb];
        constexpr uint32_t faces = pack_tile_num_faces[cb];
        _llk_pack_reconfig_data_format_<DST_ACCUM_MODE>(
            src, dst, get_local_cb_interface(cb).fifo_page_size, c_dim, faces, false
        );
#endif
    }

    // The column's sum (DST 0) packed onto own sums tile `at`: the first write of a
    // tile overwrites it, later ones add to it in L1.
    inline void pack_sum(uint32_t at) {
        const uint32_t bit = 1u << (at % 32);
        const bool again = (touched[at / 32] & bit) != 0;
        pack_format<kFieldSums>();
        pack_reconfig_l1_acc(again ? 1 : 0);
        pack_tile<true>(0, kFieldSums, at);
        pack_reconfig_l1_acc(0);
        touched[at / 32] |= bit;
    }

    // One tile of an entry's first stream: a dense slice's columns (K tiles each, into
    // the sums from tile r) or V's (K tiles each, into t). `count` its tiles.
    inline void first(
        uint32_t weights,
        uint32_t index,
        uint32_t xs,
        uint32_t k,
        uint32_t count,
        uint32_t r,
        uint32_t rank
    ) {
        const Busy timed;
        setup(weights, xs, 1);
        if (place.tile == 0) {
            tile_regs_acquire();
        }
        matmul_block(weights, xs, index, place.tile, 0, 1, 1, 1, 1);
        if (++place.tile < k) {
            return;
        }
        tile_regs_commit();
        tile_regs_wait();
        if (rank == 0) {
            pack_sum(r + place.column);
        } else {
            pack_format<kFieldT>();
            pack_tile<true>(0, kFieldT, place.column);
        }
        tile_regs_release();
        place.tile = 0;
        if (++place.column * k == count) {
            place.column = 0;
            if (rank != 0) {  // t is whole: pack hands it to unpack
                cb_reserve_back(kFieldToken, 1);
                cb_push_back(kFieldToken, 1);
            }
        }
    }

    // One tile of a low-rank entry's U^T stream: R tiles a column, into the sums
    // from tile r.
    inline void second(
        uint32_t weights, uint32_t index, uint32_t rank, uint32_t count, uint32_t r
    ) {
        const Busy timed;
        if (place.tile == 0 && place.column == 0) {  // t packed by pack
            cb_wait_front(kFieldToken, 1);
            cb_pop_front(kFieldToken, 1);
        }
        setup(weights, kFieldT, 2);
        if (place.tile == 0) {
            tile_regs_acquire();
        }
        matmul_block(weights, kFieldT, index, place.tile, 0, 0, 1, 1, 1);
        if (++place.tile < rank) {
            return;
        }
        tile_regs_commit();
        tile_regs_wait();
        pack_sum(r + place.column);
        tile_regs_release();
        place.tile = 0;
        if (++place.column * rank == count) {
            place.column = 0;
        }
    }

    // The command's end: pack has packed every sum; unpack may read them.
    inline void finish() {
        cb_reserve_back(kFieldToken, 1);
        cb_push_back(kFieldToken, 1);
        cb_wait_front(kFieldToken, 1);
        cb_pop_front(kFieldToken, 1);
    }

    // Own sums tile j, turned back, packed into y's page (`out`, a block of one tile).
    template <uint32_t out>
    inline void write(uint32_t j) {
        const Busy timed;
        reconfig_data_format_srca(kFieldSums);
        copy_init(kFieldSums);
        tile_regs_acquire();
        copy_tile(kFieldSums, j, 0);
        transpose_dest_init<DST_ACCUM_MODE, true>();
        transpose_dest<DST_ACCUM_MODE, true>(0);
        tile_regs_commit();
        tile_regs_wait();
        pack_format<out>();
        pack_tile(0, out);
        tile_regs_release();
        place.setup = 0;  // the copy and the turn changed the units' set-up
    }

    // The command's stamps (wall-clock cycles): unpack's span, busy, start and end,
    // handed to pack by mailbox, then pack's own, into the core's profile page.
    inline void hand() {
        const uint32_t ended = km::wall();
        const uint32_t words[4] = {ended - started, busy, started, ended};
        for (uint32_t word : words) {
            ckernel::mailbox_write(ckernel::ThreadId::PackThreadId, word);
        }
    }

    inline void report(uint32_t page) {
        const uint32_t ended = km::wall();
        volatile tt_l1_ptr uint32_t* words = km::l1(page);
        for (uint32_t i = 0; i < 4; i++) {
            const uint32_t word = (ckernel::mailbox_read(
                ckernel::ThreadId::UnpackThreadId
            ));
            if (page != 0) {
                words[i] = word;
            }
        }
        if (page != 0) {
            words[4] = ended - started;
            words[5] = busy;
            words[6] = started;
            words[7] = ended;
        }
    }

    // The apply of one command on the three compute CPUs.
    template <typename Compute>
    inline void apply_compute(const Compute& compute, const km_command_t& command) {
        [[maybe_unused]] Windows windows;  // the frame program's places
        static_cast<void>(command);
#if defined(TRISC_MATH)
        // Dst cleared whole, as pack's release clears a section: the first products
        // add to it
        ckernel::addr_mod_t{
            .srca = {.incr = 0}, .srcb = {.incr = 0}, .dest = {.incr = 0}
        }
            .set(ADDR_MOD_1);
        TTI_ZEROACC(p_zeroacc::CLR_ALL, DST_ACCUM_MODE, 0, ADDR_MOD_1, 0);
        TTI_STALLWAIT(p_stall::STALL_SFPU | p_stall::STALL_SYNC, p_stall::MATH);
#endif
#if defined(TRISC_PACK)
        cb_reserve_back(kFieldSums, kConstOwn);  // pack writes both in place
        cb_reserve_back(kFieldT, kConstRank);
#endif
        bool ok = true;
        begin();
        for (uint32_t p = 0; ok && p < kConstPages; p++) {
            if (!compute.wait_front(kFieldTable, 1)) {
                return;
            }
            const volatile tt_l1_ptr uint32_t* page = (km::l1(
                get_tile_address(kFieldTable, 0)
            ));
            invalidate_l1_cache();
            const uint32_t count = entries(page);
            for (uint32_t at = 0; ok && at < count; at++) {
                const volatile tt_l1_ptr uint32_t* e = entry(page, at);
                const uint32_t k = e[kK];
                const uint32_t a = e[kA];
                const uint32_t b = e[kB];
                const uint32_t r = e[kR];
                const uint32_t rank = e[kRankWord];
                const uint32_t held = km::block_half(kPairXIn, kReadPattern, 0);
                ok = compute.wait_front(held, kConstKmax);
                const uint32_t blocks_a = (a + kConstBlock - 1) / kConstBlock;
                for (uint32_t block = 0; ok && block < blocks_a; block++) {
                    const uint32_t half = km::block_half(kPairWIn, kReadPattern, block);
                    ok = compute.wait_front(half, kConstBlock);
                    if (!ok) {
                        break;
                    }
                    const uint32_t valid =
                        (block + 1 == blocks_a ? a - block * kConstBlock : kConstBlock);
                    for (uint32_t tile = 0; tile < valid; tile++) {
                        first(half, tile, held, k, a, r, rank);
                    }
                    cb_pop_front(half, kConstBlock);
                }
                const uint32_t blocks_b = (b + kConstBlock - 1) / kConstBlock;
                for (uint32_t block = 0; ok && block < blocks_b; block++) {
                    const uint32_t half = km::block_half(kPairWIn, kReadPattern, block);
                    ok = compute.wait_front(half, kConstBlock);
                    if (!ok) {
                        break;
                    }
                    const uint32_t valid =
                        (block + 1 == blocks_b ? b - block * kConstBlock : kConstBlock);
                    for (uint32_t tile = 0; tile < valid; tile++) {
                        second(half, tile, rank, b, r);
                    }
                    cb_pop_front(half, kConstBlock);
                }
                if (ok) {  // the held block freed at the entry's end
                    cb_pop_front(held, kConstKmax);
                }
            }
            cb_pop_front(kFieldTable, 1);
        }
        if (!compute.wait_front(kFieldHead, 1)) {
            return;
        }
        const volatile tt_l1_ptr uint32_t* head = (km::l1(
            get_tile_address(kFieldHead, 0)
        ));
        invalidate_l1_cache();
        const uint32_t own = head[kHeadOwn];
        finish();
        for (uint32_t j = 0; ok && j < own; j++) {
            const bool room = compute.reserve_back(kFieldYPage, 1);
            write<kFieldYPage>(j);
            if (room) {
                cb_push_back(kFieldYPage, 1);
            }
        }
        cb_pop_front(kFieldHead, 1);
#if defined(TRISC_UNPACK)
        hand();
#endif
        const bool room = compute.reserve_back(kFieldApplyProfile, 1);
#if defined(TRISC_PACK)
        report(room ? get_local_cb_interface(kFieldApplyProfile).fifo_wr_ptr << 4 : 0);
#endif
        if (room) {
            cb_push_back(kFieldApplyProfile, 1);
        }
    }

}  // namespace apply_k
