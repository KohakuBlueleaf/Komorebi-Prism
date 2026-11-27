/* A DEPTH view's levels of nearest depth: each level's texel the largest 1/z of the 2 x
 * 2 below it (no 1/z is negative, so their bits order as their values). A tile's levels
 * 16 x 16 down to 1 x 1 are its slot (a page of DEPTH_LEVELS_SLOT_BYTES of the levels'
 * tensor), each row-major from its word below; a tile's top (a page of
 * DEPTH_LEVELS_TOP_BYTES of the tops' tensor) its 1 x 1 and a mark that the slot is
 * whole. Read by the tile thread's depth step (it writes them) and the X280 (it ends a
 * tile drawn in bands and reduces the tops). */
#pragma once

#include <stdint.h>

#define DEPTH_LEVELS_SLOT_BYTES 2048u
#define DEPTH_LEVELS_TOP_BYTES 64u
#define DEPTH_LEVELS_TILE 32u   /* a tile's side, a map page's */
#define DEPTH_LEVELS_IN_TILE 5u /* the levels a tile holds: 16 x 16 to 1 x 1 */
#define DEPTH_LEVELS_L1 0u      /* 16 x 16 */
#define DEPTH_LEVELS_L2 256u    /* 8 x 8 */
#define DEPTH_LEVELS_L3 320u    /* 4 x 4 */
#define DEPTH_LEVELS_L4 336u    /* 2 x 2 */
#define DEPTH_LEVELS_L5 340u    /* 1 x 1 */
#define DEPTH_LEVELS_WORDS 341u
#define DEPTH_LEVELS_WRITTEN 1376u /* the words written, on 16 bytes */
#define DEPTH_LEVELS_TOP_VALUE 0u  /* a top's words: the 1 x 1 */
#define DEPTH_LEVELS_TOP_WHOLE 1u  /*   1 when the slot is whole */

/* The larger of two 1/z by their bits. */
static inline uint32_t depth_levels_most(uint32_t a, uint32_t b) {
    return a > b ? a : b;
}

/* The tile's levels 8 x 8 to 1 x 1 of `slot` from its 16 x 16. */
static inline void depth_levels_below(uint32_t* slot) {
    uint32_t from = DEPTH_LEVELS_L1, to = DEPTH_LEVELS_L2, side = 16u;
    while (side > 1u) {
        const uint32_t half = side / 2u;
        for (uint32_t y = 0; y < half; y++) {
            for (uint32_t x = 0; x < half; x++) {
                const uint32_t* a = slot + from + 2u * y * side + 2u * x;
                slot[to + y * half + x] = depth_levels_most(
                    depth_levels_most(a[0], a[1]),
                    depth_levels_most(a[side], a[side + 1u])
                );
            }
        }
        from = to;
        to += half * half;
        side = half;
    }
}
