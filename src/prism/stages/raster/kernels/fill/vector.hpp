// The pack thread's part of FILL: the vector unit's registers and Dst layout, its
// state, a tile's start and a record's copy. All raw Tensix instructions.
#pragma once

#include <stdint.h>

#include "ckernel.h"
#include "ckernel_addrmod.h"
#ifndef ARCH_WORMHOLE
#include "ckernel_dest.h"
#endif
#include "ckernel_ops.h"
#include "komorebi/device/km_dst.hpp"
#ifdef ARCH_WORMHOLE
#include "lltt.h"
#endif

#if defined(__riscv_vector)
#include <riscv_vector.h>
#endif

#include "../common/layouts.hpp"

namespace fill_k {

    namespace fill {

        using namespace ckernel;

        // LRegs: L0, L1 work; L2 to L4 edge thresholds, L5 triangle number (in rows);
        // L6 = -0, L7 = py; 9 = +0, 10 = 1.0, 12 = -0's neighbour 0x80000001, 15 = 2
        // lane.
        constexpr uint32_t L0 = 0, L1 = 1, L2 = 2, L3 = 3, L4 = 4, L5 = 5, NZ = 6,
                           PY = 7;
        constexpr uint32_t ZERO = 9, ONE = 10, TNEG = 12, LANE = 15;
        constexpr uint32_t kInt32 = 4;  // SFPLOAD / SFPSTORE: 32 bits as they are
#ifdef ARCH_WORMHOLE
        constexpr uint32_t
            kAddressMode = ADDR_MOD_3;  // 7: ADDR_MOD_SET_Base set (setup)
#else
        constexpr uint32_t kAddressMode = ADDR_MOD_7;
#endif
        constexpr uint32_t kFloatB = 0, kFloatA = 1, kUShort = 2, kLower = 10;
        constexpr uint32_t kSetCC = 1;  // SFPGT: lanes stay enabled where VD > VC
        constexpr uint32_t kWallClock = 0xFFB121F0;

        // Dst vectors: plane p row r at 32 p + r (depth, red, green, blue, triangle),
        // py of row r at 160 + r, the triangle's broadcast constants from 192.
        constexpr uint32_t kVecPy = 160;
        constexpr uint32_t kVecConstants = 192;
        constexpr uint32_t kConstA = 0;
        constexpr uint32_t kConstB = 3;
        constexpr uint32_t kConstC = 6;
        constexpr uint32_t kConstW = 9;
        constexpr uint32_t kConstColourA = 12;
        constexpr uint32_t kConstColourB = 15;
        constexpr uint32_t kConstColourC = 18;
        constexpr uint32_t kConstPx = 21;

        // Dst address of `vector`: an aligned group of four rows, even or odd columns.
        constexpr uint32_t dst_address(uint32_t vector) {
            return 4 * (vector >> 1) + 2 * (vector & 1);
        }

        constexpr uint32_t constant_address(uint32_t index) {
            return dst_address(kVecConstants + index);
        }

        inline uint32_t wall() {
            return *reinterpret_cast<volatile uint32_t*>(kWallClock);
        }

#if defined(__riscv_vector)
        // A record's copy on the pack core's vector extension, 32 words per
        // instruction.
        inline void copy_words_rvv(
            uint32_t* destination, const uint32_t* source, uint32_t words
        ) {
            const size_t vector_length = __riscv_vsetvl_e32m8(32);
            for (uint32_t i = 0; i < words; i += 32) {
                __riscv_vse32_v_u32m8(
                    destination + i,
                    __riscv_vle32_v_u32m8(source + i, vector_length),
                    vector_length
                );
            }
            asm volatile("" ::: "memory");
        }
#endif

#ifdef ARCH_WORMHOLE
        // Wormhole holds no MAD-class result for a read the next cycle
        // (chips.wormhole_hold).
#define FILL_HOLD TTI_SFPNOP

        // SFPGT(0, c, d, kSetCC) in Wormhole's words, the tile compiler's (hazards/
        // wormhole.py, _less): lanes stay enabled where c < d as sign-magnitude
        // integers.
#define FILL_LESS(c, d, a, b)    \
    TTI_SFPMOV(0, c, a, 0);      \
    TTI_SFPSHFT(0xFE1, 0, a, 1); \
    TTI_SFPIADD(0, ZERO, a, 6);  \
    TTI_SFPMOV(0, d, b, 0);      \
    TTI_SFPIADD(0, c, b, 6);     \
    TTI_SFPIADD(0, a, b, 4);     \
    TTI_SFPXOR(0, a, b, 0);      \
    TTI_SFPMOV(0, c, a, 0);      \
    TTI_SFPXOR(0, d, a, 0);      \
    TTI_SFPXOR(0, c, b, 0);      \
    TTI_SFPAND(0, b, a, 0);      \
    TTI_SFPXOR(0, c, b, 0);      \
    TTI_SFPXOR(0, a, b, 0);      \
    TTI_SFPSETCC(0, b, 0, 0)

        // The same with one free register `a` (_less_by_lanes): r by the signs' lanes,
        // the flags kept on their stack meanwhile.
#define FILL_LESS_LANES(c, d, a) \
    TTI_SFPPUSHC(0, 0, 0, 0);    \
    TTI_SFPENCC(3, 0, 0, 10);    \
    TTI_SFPMOV(0, d, a, 0);      \
    TTI_SFPSETCC(0, c, 0, 4);    \
    TTI_SFPIADD(0, c, a, 6);     \
    TTI_SFPSETCC(0, d, 0, 0);    \
    TTI_SFPMOV(0, c, a, 0);      \
    TTI_SFPENCC(3, 0, 0, 10);    \
    TTI_SFPSETCC(0, c, 0, 0);    \
    TTI_SFPMOV(0, c, a, 0);      \
    TTI_SFPSETCC(0, d, 0, 0);    \
    TTI_SFPIADD(0, d, a, 6);     \
    TTI_SFPPOPC(0, 0, 0, 0);     \
    TTI_SFPSETCC(0, a, 0, 0)
#else
#define FILL_HOLD
#endif

        // Thread state: no address step, Dst offset 0, 32-bit window, every lane
        // enabled; L6 = -0, L12 = 0x80000001.
        inline void setup() {
            addr_mod_t{.srca = {.incr = 0}, .srcb = {.incr = 0}, .dest = {.incr = 0}}
                .set(ADDR_MOD_7);
            TTI_SETC16(DEST_TARGET_REG_CFG_MATH_Offset_ADDR32, 0);
            TTI_SETRWC(p_setrwc::CLR_NONE, 0, 0, 0, 0, p_setrwc::SET_D);
#ifdef ARCH_WORMHOLE
            TTI_SETC16(ADDR_MOD_SET_Base_ADDR32, 1);  // kAddressMode is mode 7
#else
            configure_dest_access<ThreadId::PackThreadId>(DataFormat::Float32, true);
#endif
            TTI_SFPENCC(3, 0, 0, 10);
            TTI_SFPLOADI(NZ, kFloatB, 0x8000);
            TTI_SFPLOADI(L0, kFloatB, 0x8000);
            TTI_SFPLOADI(L0, kLower, 0x0001);
            TTI_SFPNOP;
            TTI_SFPCONFIG(0, TNEG, 0);
            TTI_SFPNOP;
            tensix_sync();
        }

        inline void finish() {
            TTI_SFPENCC(3, 0, 0, 10);
            TTI_SFPNOP;
#ifdef ARCH_WORMHOLE
            TTI_SETC16(ADDR_MOD_SET_Base_ADDR32, 0);
#endif
            tensix_sync();
        }

        // A float32 bit pattern into an LReg (two immediates; one when the low half is
        // 0).
        inline void load_f32(uint32_t lreg, uint32_t bits) {
            TT_SFPLOADI(lreg, kFloatB, bits >> 16);
            if (bits & 0xFFFF) {
                TT_SFPLOADI(lreg, kLower, bits & 0xFFFF);
            }
        }

        inline void load_vec(uint32_t lreg, uint32_t vector) {
            TT_SFPLOAD(lreg, kInt32, kAddressMode, dst_address(vector));
        }

        inline void store_vec(uint32_t lreg, uint32_t vector) {
            TT_SFPSTORE(lreg, kInt32, kAddressMode, dst_address(vector));
        }

        // Cycles of the pack thread, by phase (wall clock).
        struct ProfileCounters {
            uint32_t wait_in = 0;         // waiting for list pages
            uint32_t init = 0;            // planes, px and py of a tile
            uint32_t triangle_setup = 0;  // a triangle's constants
            uint32_t rows = 0;            // the row bodies
            uint32_t drain = 0;           // vector unit finishing before the read-out
            uint32_t out = 0;             // planes from Dst to the output pages
            uint32_t wait_out = 0;        // waiting for free output pages
            uint32_t tiles = 0;
            uint32_t triangles = 0;
            uint32_t row_count = 0;
            uint32_t total = 0;
        };

        // Planes of tile (tile_x, tile_y) to their empty values; py of its rows and px
        // of its columns into Dst.
        inline void init_tile(
            uint32_t tile_x, uint32_t tile_y, const uint32_t* background
        ) {
            TTI_SFPENCC(3, 0, 0, 10);
            TTI_SFPLOADI(L0, kFloatB, 0);       // depth 0
            TTI_SFPLOADI(L4, kFloatB, 0xBF80);  // triangle -1
            load_f32(L1, background[0]);
            load_f32(L2, background[1]);
            load_f32(L3, background[2]);
            for (uint32_t row = 0; row < 32; ++row) {
                store_vec(L0, row);
                store_vec(L1, 32 + row);
                store_vec(L2, 64 + row);
                store_vec(L3, 96 + row);
                store_vec(L4, 128 + row);
            }
            // py of a row = 32 tile_y + row + 0.5, by exact additions of 1.
            const float origin_y = 32.0f * tile_y + 0.5f;
            const float origin_x = 32.0f * tile_x + 0.5f;
            uint32_t origin_y_bits, origin_x_bits;
            __builtin_memcpy(&origin_y_bits, &origin_y, 4);
            __builtin_memcpy(&origin_x_bits, &origin_x, 4);
            load_f32(L5, origin_y_bits);
            for (uint32_t row = 0; row < 32; ++row) {
                store_vec(L5, kVecPy + row);
                TTI_SFPMAD(L5, ONE, ONE, L5, 0);
                FILL_HOLD;
            }
            // px of lane l = 32 tile_x + l + 0.5 = (2 l) * 0.5 + origin_x, exact.
            TTI_SFPCAST(LANE, L0, 0);
            TTI_SFPLOADI(L1, kFloatB, 0x3F00);
            load_f32(L2, origin_x_bits);
            TTI_SFPMAD(L0, L1, L2, L0, 0);
            TTI_SFPNOP;
            store_vec(L0, kVecConstants + kConstPx);
        }

        inline void push(uint32_t instruction) {
            instrn_buffer[0] = instruction;
        }

        // A float32 bit pattern into an LReg: upper half (lower half zeroed), lower
        // half.
        inline void immediate(uint32_t lreg, uint32_t bits) {
            push(TT_OP_SFPLOADI(lreg, kFloatB, bits >> 16));
            push(TT_OP_SFPLOADI(lreg, kLower, bits & 0xFFFF));
        }

        // Copies a 32-word record to local memory, loads grouped ahead of their use.
        inline void fetch(uint32_t* words, const volatile uint32_t* record) {
#pragma GCC unroll 4
            for (uint32_t i = 0; i < kSlotWords; i += 8) {
                uint32_t loaded[8];
#pragma GCC unroll 8
                for (uint32_t j = 0; j < 8; ++j) {
                    loaded[j] = record[i + j];
                }
#pragma GCC unroll 8
                for (uint32_t j = 0; j < 8; ++j) {
                    words[i + j] = loaded[j];
                }
            }
        }

    }  // namespace fill

}  // namespace fill_k
