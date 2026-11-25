// The pack thread's part of FILL, continued: a triangle's constants into Dst, and
// a row's edge tests, depth test and planes.
#pragma once

#include "vector.hpp"

namespace fill_k {

    namespace fill {

        // The box columns' test of edge 0: x0 < px < x1 (L2, L5, L4) keeps lanes
        // enabled; on Wormhole L0 and PY are free there (PY is loaded again by each
        // row).
#ifdef ARCH_WORMHOLE
#define FILL_BOX               \
    FILL_LESS(L2, L5, L0, PY); \
    FILL_LESS(L5, L4, L0, PY)
#else
#define FILL_BOX                  \
    TTI_SFPGT(0, L2, L5, kSetCC); \
    TTI_SFPGT(0, L5, L4, kSetCC)
#endif

        // The box columns of `record_words` into L2 and L4: masked float16 immediates,
        // or in a wide build (grid.h) float32 ones, two immediates each.
#ifdef RASTER_WIDE
#define FILL_COLUMNS                     \
    immediate(L2, record_words[kRecX0]); \
    immediate(L4, record_words[kRecX1])
#else
#define FILL_COLUMNS                                                  \
    push(TT_OP_SFPLOADI(L2, kFloatA, record_words[kRecX0] & 0xFFFF)); \
    push(TT_OP_SFPLOADI(L4, kFloatA, record_words[kRecX1] & 0xFFFF))
#endif

        // Edge `edge` of `record_words`: a px into constants[kConstA + edge] (through
        // LReg `lreg`), b, c and T broadcast; FILL_COLUMNS the box's.
#define FILL_TRI_EDGE(edge, lreg)                                               \
    immediate(lreg, record_words[kRecA + edge]);                                \
    TTI_SFPMAD(lreg, L5, NZ, lreg, 0);                                          \
    if (edge == 0) {                                                            \
        FILL_COLUMNS;                                                           \
        TTI_SFPLOADI(L3, kFloatB, 0xFF80);                                      \
        FILL_BOX;                                                               \
        TTI_SFPLOADI(L3, kFloatB, 0);                                           \
        TTI_SFPENCC(3, 0, 0, 10);                                               \
        TTI_SFPMAD(lreg, ONE, L3, lreg, 0);                                     \
    }                                                                           \
    FILL_HOLD;                                                                  \
    TTI_SFPSTORE(lreg, kInt32, kAddressMode, constant_address(kConstA + edge)); \
    immediate(L2, record_words[kRecB + edge]);                                  \
    TTI_SFPSTORE(L2, kInt32, kAddressMode, constant_address(kConstB + edge));   \
    immediate(L3, record_words[kRecC + edge]);                                  \
    TTI_SFPSTORE(L3, kInt32, kAddressMode, constant_address(kConstC + edge))

#define FILL_TRI_COLOUR(colour, lreg)                                                 \
    immediate(lreg, record_words[kRecCol + 3 * colour]);                              \
    TTI_SFPMAD(lreg, L5, NZ, lreg, 0);                                                \
    immediate(L2, record_words[kRecCol + 3 * colour + 1]);                            \
    TTI_SFPSTORE(L2, kInt32, kAddressMode, constant_address(kConstColourB + colour)); \
    immediate(L3, record_words[kRecCol + 3 * colour + 2]);                            \
    TTI_SFPSTORE(L3, kInt32, kAddressMode, constant_address(kConstColourC + colour)); \
    TTI_SFPSTORE(lreg, kInt32, kAddressMode, constant_address(kConstColourA + colour))

        // The broadcast constants of one triangle record (local copy `record_words`)
        // into Dst, its thresholds and number into L2 to L5. Edge 0's a px is -inf off
        // the box.
        inline void load_triangle(const uint32_t* record_words) {
            TTI_SFPLOAD(L5, kInt32, kAddressMode, constant_address(kConstPx));
            FILL_TRI_EDGE(0, L1);
            FILL_TRI_EDGE(1, L0);
            FILL_TRI_EDGE(2, L1);
            immediate(L0, record_words[kRecW]);
            TTI_SFPMAD(L0, L5, NZ, L0, 0);
            immediate(L2, record_words[kRecW + 1]);
            TTI_SFPSTORE(L2, kInt32, kAddressMode, constant_address(kConstW + 1));
            immediate(L3, record_words[kRecW + 2]);
            TTI_SFPSTORE(L3, kInt32, kAddressMode, constant_address(kConstW + 2));
            TTI_SFPSTORE(L0, kInt32, kAddressMode, constant_address(kConstW));
            FILL_TRI_COLOUR(0, L1);
            FILL_TRI_COLOUR(1, L0);
            FILL_TRI_COLOUR(2, L1);
            for (uint32_t edge = 0; edge < 3; ++edge) {
                push(TT_OP_SFPMOV(
                    0, record_words[kRecT + edge] != 0 ? TNEG : ZERO, L2 + edge, 0
                ));
            }
            immediate(L5, record_words[kRecTri]);
        }

        // value = (A + B py) + C into L0, the constants at the vectors `constant_a`,
        // `constant_b`, `constant_c`.
#define FILL_PLANE(constant_a, constant_b, constant_c)                   \
    TTI_SFPLOAD(L0, kInt32, kAddressMode, constant_address(constant_b)); \
    TTI_SFPMAD(L0, PY, NZ, L0, 0);                                       \
    TTI_SFPLOAD(L1, kInt32, kAddressMode, constant_address(constant_a)); \
    TTI_SFPMAD(L1, ONE, L0, L0, 0);                                      \
    TTI_SFPLOAD(L1, kInt32, kAddressMode, constant_address(constant_c)); \
    TTI_SFPMAD(L0, ONE, L1, L0, 0)

#ifdef ARCH_WORMHOLE
#define FILL_EDGE(edge)                                         \
    FILL_PLANE(kConstA + edge, kConstB + edge, kConstC + edge); \
    FILL_LESS_LANES(L2 + edge, L0, L1)

        // A row's edge tests and 1/z plane: 66 instructions, the first 26 (edge 0, edge
        // 1's plane) recorded once into the 32-entry replay buffer (record) or played.
        constexpr uint32_t kReplayEdges = 26;

        inline void edges(bool record) {
            if (record) {
                lltt::record(0, kReplayEdges);
                FILL_EDGE(0);
                FILL_PLANE(kConstA + 1, kConstB + 1, kConstC + 1);
                return;
            }
            lltt::replay(0, kReplayEdges);
            FILL_LESS_LANES(L3, L0, L1);
            FILL_EDGE(2);
            FILL_PLANE(kConstW, kConstW + 1, kConstW + 2);
        }

        // The depth test, L1 < L0: PY is the free register, loaded again after it.
#define FILL_DEPTH(pixel_row)    \
    FILL_LESS_LANES(L1, L0, PY); \
    TT_SFPLOAD(PY, kInt32, kAddressMode, dst_address(kVecPy + pixel_row))

        // Around the packer's reads: ADDR_MOD_SET_Base would move PACR's address modes
        // too.
        inline void packing(bool start) {
            TTI_SETC16(ADDR_MOD_SET_Base_ADDR32, start ? 0 : 1);
            if (start) {
                tensix_sync();
            }
        }
#else
#define FILL_EDGE(edge)                                         \
    FILL_PLANE(kConstA + edge, kConstB + edge, kConstC + edge); \
    TTI_SFPGT(0, L2 + edge, L0, kSetCC)

        // A row's edge tests and 1/z plane: 27 instructions, recorded once into the
        // replay buffer (record) or played (not record).
        constexpr uint32_t kReplayEdges = 27;

        inline void edges(bool record) {
            if (record) {
                TTI_REPLAY(0, kReplayEdges, 0, 1);
                FILL_EDGE(0);
                FILL_EDGE(1);
                FILL_EDGE(2);
                FILL_PLANE(kConstW, kConstW + 1, kConstW + 2);
            } else {
                TTI_REPLAY(0, kReplayEdges, 0, 0);
            }
        }

#define FILL_DEPTH(pixel_row) TTI_SFPGT(0, L1, L0, kSetCC)
#endif

        // Row `pixel_row` (masked to its field) against the triangle in the constant
        // vectors: the inside lanes nearer than the depth take its depth, number,
        // colour.
        inline void row(uint32_t pixel_row) {
            pixel_row &= 31;
            TT_SFPLOAD(PY, kInt32, kAddressMode, dst_address(kVecPy + pixel_row));
            edges(false);
            TT_SFPLOAD(L1, kInt32, kAddressMode, dst_address(pixel_row));
            FILL_DEPTH(pixel_row);
            TT_SFPSTORE(L0, kInt32, kAddressMode, dst_address(pixel_row));
            TT_SFPSTORE(L5, kInt32, kAddressMode, dst_address(128 + pixel_row));
            FILL_PLANE(kConstColourA, kConstColourB, kConstColourC);
            FILL_HOLD;
            TT_SFPSTORE(L0, kInt32, kAddressMode, dst_address(32 + pixel_row));
            FILL_PLANE(kConstColourA + 1, kConstColourB + 1, kConstColourC + 1);
            FILL_HOLD;
            TT_SFPSTORE(L0, kInt32, kAddressMode, dst_address(64 + pixel_row));
            FILL_PLANE(kConstColourA + 2, kConstColourB + 2, kConstColourC + 2);
            FILL_HOLD;
            TT_SFPSTORE(L0, kInt32, kAddressMode, dst_address(96 + pixel_row));
            TTI_SFPENCC(3, 0, 0, 10);
        }

    }  // namespace fill

}  // namespace fill_k
