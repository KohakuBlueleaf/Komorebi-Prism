// Visibility's row on the pack CPU: the walk's row (fill/triangle.hpp)
// with a depth test that decides ties, so a layer's records may come in any order: a
// lane takes the record where its 1/z is greater than the one held, or equal with a
// lower triangle number than the one held.
#pragma once

#include <stdint.h>

#include "../../kernels/fill/walk.hpp"

namespace visibility_step {

    namespace row_k {

        using namespace fill_k::fill;

        // The tie-deciding depth test, L0 the record's 1/z, L1 the held one, L5 the
        // record's triangle number: d = L0 - L1, where d == 0 d = held number - L5;
        // lanes stay enabled where d > 0. PY is the free register, loaded again.
#ifdef ARCH_WORMHOLE
#define FILL_DEPTH_TIED(pixel_row)                                         \
    TTI_SFPPUSHC(0, 0, 0, 0);                                              \
    TTI_SFPMOV(0, L1, L1, 1);                                              \
    TTI_SFPMAD(L1, ONE, L0, L1, 0);                                        \
    FILL_HOLD;                                                             \
    TTI_SFPSETCC(0, L1, 0, 6);                                             \
    TT_SFPLOAD(PY, kInt32, kAddressMode, dst_address(128 + pixel_row));    \
    TTI_SFPMOV(0, PY, PY, 1);                                              \
    TTI_SFPMAD(L5, ONE, PY, L1, 0);                                        \
    FILL_HOLD;                                                             \
    TTI_SFPMOV(0, L1, L1, 1);                                              \
    TT_SFPLOAD(PY, kInt32, kAddressMode, dst_address(kVecPy + pixel_row)); \
    TTI_SFPPOPC(0, 0, 0, 0);                                               \
    TTI_SFPSETCC(0, L1, 0, 4);                                             \
    TTI_SFPSETCC(0, L1, 0, 2)
#else
#define FILL_DEPTH_TIED(pixel_row)                                         \
    TTI_SFPPUSHC(0, 0, 0, 0);                                              \
    TTI_SFPMAD(L1, ONE, L0, L1, 1);                                        \
    TTI_SFPSETCC(0, L1, 0, 6);                                             \
    TT_SFPLOAD(PY, kInt32, kAddressMode, dst_address(128 + pixel_row));    \
    TTI_SFPMAD(L5, ONE, PY, L1, 1);                                        \
    TT_SFPLOAD(PY, kInt32, kAddressMode, dst_address(kVecPy + pixel_row)); \
    TTI_SFPPOPC(0, 0, 0, 0);                                               \
    TTI_SFPGT(0, ZERO, L1, kSetCC)
#endif

        // Row `pixel_row` (masked to its field) against the triangle in the constant
        // vectors: the inside lanes the record wins take its depth, number, colour.
        inline void row(uint32_t pixel_row) {
            pixel_row &= 31;
            TT_SFPLOAD(PY, kInt32, kAddressMode, dst_address(kVecPy + pixel_row));
            edges(false);
            TT_SFPLOAD(L1, kInt32, kAddressMode, dst_address(pixel_row));
            FILL_DEPTH_TIED(pixel_row);
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

    }  // namespace row_k

    // A record's rows in the walk's tile (fill_k::Walk::record with the row above).
    inline void record(fill_k::Walk& walk, const volatile uint32_t* record) {
        using namespace fill_k;
        const uint32_t before = fill::wall();
        uint32_t record_words[kSlotWords];
#if defined(__riscv_vector)
        fill::copy_words_rvv(
            record_words, const_cast<const uint32_t*>(record), kSlotWords
        );
#else
        fill::fetch(record_words, record);
#endif
        const int32_t box_first_row =
            (static_cast<int32_t>(record_words[kRecY0]) - 32 * walk.tile_y);
        const int32_t box_last_row =
            (static_cast<int32_t>(record_words[kRecY1]) - 32 * walk.tile_y);
        const int32_t first_covered =
            (box_first_row < walk.first_row ? walk.first_row : box_first_row);
        const int32_t last_covered =
            (box_last_row > walk.end_row - 1 ? walk.end_row - 1 : box_last_row);
        fill::load_triangle(record_words);
        const uint32_t after = fill::wall();
        walk.counters.triangle_setup += after - before;
        for (
            int32_t pixel_row = first_covered; pixel_row <= last_covered; ++pixel_row
        ) {
            row_k::row(pixel_row);
            walk.counters.row_count++;
        }
        walk.counters.rows += fill::wall() - after;
        walk.counters.triangles++;
    }

}  // namespace visibility_step
