/* A DEPTH view's T (prism_reference.direct.transmit kept): the light its glass lets
 * through to its nearest opaque surface, kept at half resolution in 8 bits. A map
 * tile's T is a block of TRANSMIT_SIDE x TRANSMIT_SIDE texels, each the code of the
 * mean of 2 x 2 pixels (floor(255 v + 1/2)), row-major: a byte (grey, red's channel)
 * or a word (r | g << 8 | b << 16) a texel; the blocks of a map's tiles in their
 * order, as many a page as fit, from T's first page of the target. Written by the tile
 * thread's depth step, read by LIGHT's sun lookup. */
#pragma once

#include <stdint.h>

#define TRANSMIT_PAGE_BYTES 4096u
#define TRANSMIT_SIDE 16u  /* a block's texels a row: a 32-pixel tile at half */
#define TRANSMIT_ONE 255u  /* the code of T 1 */
#define TRANSMIT_CODES 16u /* COPY's form (its channels plus this): its codes only */

/* A block's row's bytes, its bytes and the blocks a page holds, for `channels` 1 or 3
 */
static inline uint32_t transmit_row_bytes(uint32_t channels) {
    return TRANSMIT_SIDE * (channels == 1u ? 1u : 4u);
}

static inline uint32_t transmit_block_bytes(uint32_t channels) {
    return TRANSMIT_SIDE * transmit_row_bytes(channels);
}

static inline uint32_t transmit_blocks_a_page(uint32_t channels) {
    return TRANSMIT_PAGE_BYTES / transmit_block_bytes(channels);
}

/* Where tile `tile` (of the map, row-major) keeps its block: page and byte */
typedef struct {
    uint32_t page, offset;
} TransmitPlace;

static inline TransmitPlace transmit_place(
    uint32_t first, uint32_t tile, uint32_t channels
) {
    const uint32_t per = transmit_blocks_a_page(channels);
    TransmitPlace place = {
        first + tile / per, tile % per * transmit_block_bytes(channels)
    };
    return place;
}
