// The frame's grid of tiles in a8 of every command but SHOW's (kernels/README.md): a
// tile is ty TX + tx, the frame rendered 32 TX x 32 TY. Included before the namespaces.
#pragma once

#include <stdint.h>

// The tiles every per-tile table holds, a multiple of 32 the load chose
// (prism.core.capacity): any grid of at most this many renders.
#ifndef RASTER_TILES
#error "RASTER_TILES: the frame's capacity in tiles, chosen at the load"
#endif
constexpr uint32_t kTileCapacity = RASTER_TILES;
static_assert(kTileCapacity > 0 && kTileCapacity % 32 == 0);

// The heavy tiles and the bands' items the tables hold, from the load's fill cores
// (card.heavy_capacity): a frame has fewer than cores / 0.33 of either.
#if !defined(RASTER_HEAVY) || !defined(RASTER_BAND_ITEMS)
#error "RASTER_HEAVY, RASTER_BAND_ITEMS: from the load's fill cores"
#endif
constexpr uint32_t kHeavyCapacity = RASTER_HEAVY;
constexpr uint32_t kBandCapacity = RASTER_BAND_ITEMS;
static_assert(kHeavyCapacity > 0);

constexpr uint32_t kGridDefault = 32;
// Without RASTER_WIDE the narrow words (6-bit tile columns, 10-bit rows, float16 box
// columns) hold grids of at most kNarrowAcross by kNarrowDown; wider grids load wide.
constexpr uint32_t kNarrowAcross = 64;
constexpr uint32_t kNarrowDown = 32;

struct Grid {
    uint32_t across, down;
};

// Bits 0 to 3: 0, or 1 + the X280 thread's regions' bank.
inline uint32_t bank_word(uint32_t a8) {
    return a8 & 0xF;
}

// Bits 4 to 17 TX, 18 to 31 TY; 0 there is 32 (the 1,024 x 1,024 frame).
inline Grid grid_of(uint32_t a8) {
    const uint32_t across = a8 >> 4 & 0x3FFF, down = a8 >> 18;
    return {across ? across : kGridDefault, down ? down : kGridDefault};
}

// The frame's tiles TX x TY of a8 (at most the capacity): what a frame's loops over
// tiles and items cover; the capacity sizes the tables alone.
inline uint32_t grid_tiles(uint32_t a8) {
    const Grid grid = grid_of(a8);
    const uint32_t tiles = grid.across * grid.down;
    return tiles < kTileCapacity ? tiles : kTileCapacity;
}

// The tiles of a slice SUM walks.
constexpr uint32_t kSliceTiles = 16;

// The same rounded up to whole slices: COUNT's zeroing and counters.
inline uint32_t slice_tiles(uint32_t a8) {
    // at most the capacity, a multiple of 32
    return (grid_tiles(a8) + kSliceTiles - 1) & ~(kSliceTiles - 1);
}
