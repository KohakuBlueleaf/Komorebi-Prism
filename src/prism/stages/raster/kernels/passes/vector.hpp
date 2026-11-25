// The vector unit's part of COUNT and SETUP, raw instructions from the pack thread:
// its registers, slots and arithmetic, camera space, screen and rounding.
#pragma once

#include <stdint.h>

#include "ckernel.h"
#include "ckernel_addrmod.h"
#include "ckernel_dest.h"
#include "ckernel_ops.h"
#if defined(__riscv_vector)
#include <riscv_vector.h>
#endif

#include "../common/layouts.hpp"

namespace setup_k {
    namespace setup_pass {

        using namespace ckernel;

        // LRegs: L0 to L7 work registers; 9 = 0, 10 = 1.0.
        constexpr uint32_t L0 = 0, L1 = 1, L2 = 2, L3 = 3, L4 = 4, L5 = 5, L6 = 6,
                           L7 = 7;
        constexpr uint32_t ZERO = 9, ONE = 10;
        constexpr uint32_t kInt32 = 4;  // SFPLOAD / SFPSTORE: 32 bits as they are
        constexpr uint32_t kAddressMode = ADDR_MOD_7;
        constexpr uint32_t kFloatB = 0, kLower = 10;
        constexpr uint32_t kNegA = 1, kNegC = 2;  // SFPMAD
        constexpr uint32_t kSetCC = 1;            // SFPGT
        constexpr uint32_t kSign = 1;             // SFPMOV: the sign inverted
        constexpr uint32_t kCcNone = 4;           // SFPIADD
        constexpr uint32_t kLt0 = 0;              // SFPSETCC
        constexpr uint32_t kWallClock = 0xFFB121F0;
        constexpr uint32_t kDstWindow = 0xFFBD8000;

        // Dst slots of 32 lanes: block, camera (16 in every lane), camera-space
        // corners, records (kSlotRecords + w: word w), screen x, y, 1/z per corner,
        // area, 1/area.
        constexpr uint32_t kSlotColour = 9;
        constexpr uint32_t kSlotCamera = 32;
        constexpr uint32_t kSlotCameraSpace = 48;
        constexpr uint32_t kSlotRecords = 64;
        constexpr uint32_t kSlotScreen = 96;
        constexpr uint32_t kSlotArea = 106;
        constexpr uint32_t kSlotInverseArea = 107;
        // finish_lanes: per lane 1 kept, 2 crossing the near distance, else 0; the
        // box's columns as integers; the lane number as a float (written once by the
        // pack thread)
        constexpr uint32_t kSlotFlags = 108;
        constexpr uint32_t kSlotFirstColumn = 109;
        constexpr uint32_t kSlotLastColumn = 110;
        constexpr uint32_t kSlotLaneNumber = 111;
        constexpr uint32_t kSetVd = 8;           // SFPGT, SFPLE: -1 or 0 into VD
        constexpr uint32_t kShiftImmediate = 1;  // SFPSHFT: by the immediate, logical
        constexpr uint32_t kIaddSubtract = 2;    // SFPIADD: VD = VC - VD

        inline uint32_t wall() {
            return *reinterpret_cast<volatile uint32_t*>(kWallClock);
        }

        inline volatile uint32_t* window() {
            return reinterpret_cast<volatile uint32_t*>(kDstWindow);
        }

        // SFPLOAD / SFPSTORE address of `slot`, and the window word of its lane 0 (lane
        // l at + 2 l).
        constexpr uint32_t dst_address(uint32_t slot) {
            return 4 * (slot >> 1) + 2 * (slot & 1);
        }

        constexpr uint32_t word(uint32_t slot) {
            return 64 * (slot >> 1) + (slot & 1);
        }

        // Waits until earlier window stores are done (a load of `word_index`, used).
        inline void order(uint32_t word_index) {
            const uint32_t value = window()[word_index];
            asm volatile("and x0, x0, %0" : : "r"(value) : "memory");
        }

        inline void fill_slot(uint32_t slot, uint32_t value) {
            volatile uint32_t* words = window() + word(slot);
            for (uint32_t lane = 0; lane < 32; ++lane) {
                words[2 * lane] = value;
            }
        }

        // A block of kBlockSlots vectors, already in the window's order, to slots 0 on.
        inline void block_in(const uint32_t* source) {
#if defined(__riscv_vector)
            const size_t vector_length = __riscv_vsetvl_e32m8(32);
            for (uint32_t i = 0; i < kBlockSlots * 32; i += 32) {
                __riscv_vse32_v_u32m8(
                    const_cast<uint32_t*>(window() + i),
                    __riscv_vle32_v_u32m8(source + i, vector_length),
                    vector_length
                );
            }
            asm volatile("" ::: "memory");
#else
            for (uint32_t i = 0; i < kBlockSlots * 32; ++i) {
                window()[i] = source[i];
            }
#endif
            order(kBlockSlots * 32 - 1);
        }

        // The 32 record slots to 32 records of 128 bytes (word w of record l: slot
        // kSlotRecords + w, lane l), two slots per handler load of 16 lanes.
        inline void records_out(uint32_t* records) {
#if defined(__riscv_vector)
            const size_t vector_length = __riscv_vsetvl_e32m4(16);
            for (uint32_t half = 0; half < 2; ++half) {
                for (uint32_t pair = 0; pair < 16; ++pair) {
                    const auto pair_values = (__riscv_vlseg2e32_v_u32m4x2(
                        const_cast<const uint32_t*>(
                            window() + word(kSlotRecords) + 64 * pair + 32 * half
                        ),
                        vector_length
                    ));
                    __riscv_vssseg2e32_v_u32m4x2(
                        records + 512 * half + 2 * pair, 128, pair_values, vector_length
                    );
                }
            }
            asm volatile("" ::: "memory");
#else
            for (uint32_t word = 0; word < 32; ++word) {
                for (uint32_t lane = 0; lane < 32; ++lane) {
                    records
                        [32 * lane +
                         word] = (window()[word(kSlotRecords + word) + 2 * lane]);
                }
            }
#endif
        }

        // A float32 (or integer) bit pattern into an LReg as two immediates.
        inline void immediate(uint32_t lreg, uint32_t bits) {
            TT_SFPLOADI(lreg, kFloatB, bits >> 16);
            TT_SFPLOADI(lreg, kLower, bits & 0xFFFF);
        }

        inline void load(uint32_t lreg, uint32_t slot) {
            TT_SFPLOAD(lreg, kInt32, kAddressMode, dst_address(slot));
        }

        inline void store(uint32_t lreg, uint32_t slot) {
            TT_SFPSTORE(lreg, kInt32, kAddressMode, dst_address(slot));
        }

        // d = a * b, d = a + b, d = a - b: one rounding each, as separate float32
        // operations (the product's addend is -0, which keeps the sign of a zero
        // product).
        inline void mul(uint32_t a, uint32_t b, uint32_t d) {
            TT_SFPMAD(a, b, ZERO, d, kNegC);
        }

        inline void add(uint32_t a, uint32_t b, uint32_t d) {
            TT_SFPMAD(a, ONE, b, d, 0);
        }

        inline void sub(uint32_t a, uint32_t b, uint32_t d) {
            TT_SFPMAD(a, ONE, b, d, kNegC);
        }

        // d = -a, the sign bit inverted (as numpy's negation).
        inline void neg(uint32_t a, uint32_t d) {
            TT_SFPMOV(0, a, d, kSign);
        }

        // high = max(high, low), low = min(high, low).
        inline void order_pair(uint32_t high, uint32_t low) {
            TTI_SFPNOP;
            TT_SFPSWAP(0, high, low, 1);
        }

        // Thread state: no address step, Dst offset 0, 32-bit Dst, every lane enabled.
        inline void setup() {
            addr_mod_t{.srca = {.incr = 0}, .srcb = {.incr = 0}, .dest = {.incr = 0}}
                .set(ADDR_MOD_7);
            TTI_SETC16(DEST_TARGET_REG_CFG_MATH_Offset_ADDR32, 0);
            TTI_SETRWC(p_setrwc::CLR_NONE, 0, 0, 0, 0, p_setrwc::SET_D);
            configure_dest_access<ThreadId::PackThreadId>(DataFormat::Float32, true);
            TTI_SFPENCC(3, 0, 0, 10);
            TTI_SFPNOP;
            tensix_sync();
        }

        inline void finish() {
            TTI_SFPENCC(3, 0, 0, 10);
            TTI_SFPNOP;
            tensix_sync();
        }

        // y = 1 / a to nearest (|a| in [2^-126, 2^103)): estimate, two Newton steps, an
        // exact integer test for the rounding.
        inline void recip(
            uint32_t a,
            uint32_t y,
            uint32_t work0,
            uint32_t work1,
            uint32_t work2,
            uint32_t work3
        ) {
            TT_SFPARECIP(0, a, y, 0);
            TT_SFPMAD(a, y, ONE, work0, kNegA);  // e = 1 - a y
            TT_SFPMAD(y, work0, y, y, 0);        // y = y e + y
            TT_SFPMAD(a, y, ONE, work0, kNegA);
            TT_SFPMAD(y, work0, y, y, 0);
            // A, Y: significands of a and y. R = 2^47 - Y A, known mod 2^26 from the
            // low product bits; work2 = -64 R, then y moves by one where |2 R| > A.
            TT_SFPEXMAN(0, a, work0, 0);
            TT_SFPEXMAN(0, y, work1, 0);
            TT_SFPMUL24(
                work0, work1, ZERO, work2, 1
            );  // high 23 bits of the low 23-bit product
            TT_SFPMUL24(work0, work1, ZERO, work3, 0);  // its low 23 bits
            TTI_SFPNOP;
            TT_SFPIADD(0, work1, work2, kCcNone);
            TT_SFPIADD(0, work0, work2, kCcNone);
            TT_SFPSHFT(29, 0, work2, 1);
            TT_SFPSHFT(6, 0, work3, 1);
            TT_SFPIADD(0, work3, work2, kCcNone);
            TT_SFPSHFT(5, 0, work0, 1);  // 32 A
            TT_SFPMOV(0, work2, work3, 0);
            TTI_SFPPUSHC(0, 0, 0, 0);
            TT_SFPIADD(0, work0, work2, kLt0);  // 32 A - 64 R < 0: one up
            TT_SFPIADD(1, y, y, 1 | kCcNone);
            TTI_SFPPOPC(0, 0, 0, 0);
            TTI_SFPPUSHC(0, 0, 0, 0);
            TT_SFPIADD(0, work0, work3, 2 | kLt0);  // 32 A + 64 R < 0: one down
            TT_SFPIADD(0xFFF, y, y, 1 | kCcNone);
            TTI_SFPPOPC(0, 0, 0, 0);
        }

        // Camera space of every corner: d = p - eye; x = (d0 c3 + d1 c4) + d2 c5, and
        // y, z with the next two rows of the camera.
        inline void camera_space() {
            for (uint32_t corner = 0; corner < 3; ++corner) {
                for (uint32_t i = 0; i < 3; ++i) {
                    load(L0, 3 * corner + i);
                    load(L1, kSlotCamera + i);
                    sub(L0, L1, L2 + i);
                }
                for (uint32_t j = 0; j < 3; ++j) {
                    load(L5, kSlotCamera + 3 + 3 * j);
                    load(L6, kSlotCamera + 4 + 3 * j);
                    load(L7, kSlotCamera + 5 + 3 * j);
                    mul(L2, L5, L0);
                    mul(L3, L6, L1);
                    add(L0, L1, L0);
                    mul(L4, L7, L1);
                    add(L0, L1, L0);
                    store(L0, kSlotCameraSpace + 3 * corner + j);
                }
            }
        }

        // Screen x, y, 1/z per corner: inv = 1/z, x = c13 + c12 x inv, y = c14 - c12 y
        // inv; a lane with a corner short of the near distance gets numbers nobody
        // uses.
        inline void screen() {
            for (uint32_t corner = 0; corner < 3; ++corner) {
                load(L0, kSlotCameraSpace + 3 * corner + 2);
                recip(L0, L1, L2, L3, L4, L5);
                store(L1, kSlotScreen + 3 * corner + 2);
                load(L2, kSlotCamera + 12);
                load(L0, kSlotCameraSpace + 3 * corner);
                mul(L0, L1, L0);
                mul(L2, L0, L0);
                load(L3, kSlotCamera + 13);
                add(L3, L0, L0);
                store(L0, kSlotScreen + 3 * corner);
                load(L0, kSlotCameraSpace + 3 * corner + 1);
                mul(L0, L1, L0);
                mul(L2, L0, L0);
                load(L3, kSlotCamera + 14);
                sub(L3, L0, L0);
                store(L0, kSlotScreen + 3 * corner + 1);
            }
        }

        // ceil or floor of L0 (clamped to [low, high] first) as 1.5 x 2^23 + n, to
        // `slot`.
        inline void round_box(uint32_t low, uint32_t high, bool up, uint32_t slot) {
            immediate(L3, low);
            order_pair(L0, L3);
            immediate(L3, high);
            order_pair(L3, L0);
            immediate(L4, kMagic);
            add(L0, L4, L5);  // to the nearest integer
            sub(L5, L4, L6);
            TTI_SFPNOP;
            TTI_SFPPUSHC(0, 0, 0, 0);
            if (up) {
                TTI_SFPGT(0, L6, L0, kSetCC);  // rounded below the value: one up
                add(L5, ONE, L5);
            } else {
                TTI_SFPGT(0, L0, L6, kSetCC);  // rounded above the value: one down
                sub(L5, ONE, L5);
            }
            TTI_SFPPOPC(0, 0, 0, 0);
            store(L5, slot);
        }

    }  // namespace setup_pass

}  // namespace setup_k
