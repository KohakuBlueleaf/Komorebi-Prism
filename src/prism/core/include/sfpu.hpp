// The pack thread's vector unit basics (SHADE, LIGHT): its registers' names, Dst
// vectors' addresses and window words, load, store, immediates, the arithmetic, the
// thread state.
#pragma once

#include <stdint.h>

#include "ckernel.h"
#include "ckernel_addrmod.h"
#ifndef ARCH_WORMHOLE
#include "ckernel_dest.h"
#endif
#include "ckernel_ops.h"
#include "komorebi/device/km_dst.hpp"

namespace pack_sfpu {

    using namespace ckernel;

    constexpr uint32_t L0 = 0, L1 = 1, L2 = 2, L3 = 3, L4 = 4, L5 = 5, L6 = 6, L7 = 7;
    constexpr uint32_t ZERO = 9, ONE = 10;
    // LRegs 11 to 14, set by SFPCONFIG at the start: 1.5 x 2^23, its integer mask,
    // 32 and 1 / 32.
    constexpr uint32_t MAGIC = 11, MASK = 12, C32 = 13, INV32 = 14;
    constexpr uint32_t kNegZero = 6, kNegZeroNeighbour = 12;  // setup's first values
    constexpr uint32_t kInt32 = 4;
    constexpr uint32_t kAddressMode = ADDR_MOD_7;
    constexpr uint32_t kFloatB = 0, kLower = 10;
    constexpr uint32_t kNegA = 1, kNegC = 2;
    constexpr uint32_t kSetCC = 1;
    constexpr uint32_t kGte0 = 4, kEq0 = 6;  // SFPSETCC
    constexpr uint32_t kMinMax = 1;          // SFPSWAP: VC the larger, VD the smaller
    constexpr uint32_t kShiftImmediate = 1;
    constexpr uint32_t kMagicBits = 0x4B400000;

    // SFPLOAD / SFPSTORE address of Dst vector `vector`.
    constexpr uint32_t dst_address(uint32_t vector) {
        return 4 * (vector >> 1) + 2 * (vector & 1);
    }

    // The window word of Dst vector `vector`, lane 0 (lane l at + 2 l).
    constexpr uint32_t word(uint32_t vector) {
        return 64 * (vector >> 1) + (vector & 1);
    }

    inline volatile uint32_t* window() {
        return km::dst::window();
    }

    inline void load(uint32_t lreg, uint32_t vector) {
        TT_SFPLOAD(lreg, kInt32, kAddressMode, dst_address(vector));
    }

    inline void store(uint32_t lreg, uint32_t vector) {
        TT_SFPSTORE(lreg, kInt32, kAddressMode, dst_address(vector));
    }

    inline void immediate(uint32_t lreg, uint32_t bits) {
        TT_SFPLOADI(lreg, kFloatB, bits >> 16);
        TT_SFPLOADI(lreg, kLower, bits & 0xFFFF);
    }

    inline void mul(uint32_t a, uint32_t b, uint32_t d) {
        TT_SFPMAD(a, b, ZERO, d, kNegC);
    }

    inline void add(uint32_t a, uint32_t b, uint32_t d) {
        TT_SFPMAD(a, ONE, b, d, 0);
    }

    inline void sub(uint32_t a, uint32_t b, uint32_t d) {
        TT_SFPMAD(a, ONE, b, d, kNegC);
    }

    // out = floor(x) for |x| < 2^22: x rounded by 1.5 x 2^23, one less where above.
    inline void floor_to(uint32_t x, uint32_t out) {
        add(x, MAGIC, out);
        sub(out, MAGIC, out);
        TTI_SFPNOP;
        TTI_SFPPUSHC(0, 0, 0, 0);
        TT_SFPGT(0, x, out, kSetCC);
        sub(out, ONE, out);
        TTI_SFPPOPC(0, 0, 0, 0);
    }

    // x = max(x, 0), with `work` free.
    inline void at_least_zero(uint32_t x, uint32_t work) {
        TT_SFPLOADI(work, kFloatB, 0);
        TTI_SFPNOP;
        TT_SFPSWAP(0, x, work, kMinMax);
    }

    // Thread state: no address step, Dst offset 0, 32-bit Dst, every lane enabled,
    // L6 = -0 and L12 = 0x80000001 (FILL's); then LRegs 11 to 14.
    inline void setup() {
        addr_mod_t{.srca = {.incr = 0}, .srcb = {.incr = 0}, .dest = {.incr = 0}}.set(
            ADDR_MOD_7
        );
        TTI_SETC16(DEST_TARGET_REG_CFG_MATH_Offset_ADDR32, 0);
        TTI_SETRWC(p_setrwc::CLR_NONE, 0, 0, 0, 0, p_setrwc::SET_D);
#ifdef ARCH_WORMHOLE
        TTI_SETC16(ADDR_MOD_SET_Base_ADDR32, 1);
#else
        configure_dest_access<ThreadId::PackThreadId>(DataFormat::Float32, true);
#endif
        TTI_SFPENCC(3, 0, 0, 10);
        TTI_SFPLOADI(kNegZero, kFloatB, 0x8000);
        TTI_SFPLOADI(L0, kFloatB, 0x8000);
        TTI_SFPLOADI(L0, kLower, 0x0001);
        TTI_SFPNOP;
        TTI_SFPCONFIG(0, kNegZeroNeighbour, 0);
        TTI_SFPNOP;
        tensix_sync();
        immediate(L0, kMagicBits);
        TTI_SFPNOP;
        TTI_SFPCONFIG(0, MAGIC, 0);
        TTI_SFPNOP;
        immediate(L0, 0x003FFFFF);
        TTI_SFPNOP;
        TTI_SFPCONFIG(0, MASK, 0);
        TTI_SFPNOP;
        immediate(L0, 0x42000000);
        TTI_SFPNOP;
        TTI_SFPCONFIG(0, C32, 0);
        TTI_SFPNOP;
        immediate(L0, 0x3D000000);
        TTI_SFPNOP;
        TTI_SFPCONFIG(0, INV32, 0);
        TTI_SFPNOP;
        tensix_sync();
    }

    // The thread state back: every lane enabled.
    inline void finish() {
        TTI_SFPENCC(3, 0, 0, 10);
        TTI_SFPNOP;
#ifdef ARCH_WORMHOLE
        TTI_SETC16(ADDR_MOD_SET_Base_ADDR32, 0);
#endif
        tensix_sync();
    }

}  // namespace pack_sfpu
