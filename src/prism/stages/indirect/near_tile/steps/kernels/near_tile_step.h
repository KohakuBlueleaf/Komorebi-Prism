// The near tile step of the tile thread: its rings, its plane's words and its give-up
// places. Its words are the build's defines (PRISM_TF_NEAR_TILE_*).
#pragma once

#include <stdint.h>

namespace near_tile_step {

    // The plane near.light: E, a channel's 256 half pixels (16 x 16, row by row) after
    // another as float32 from word 0; the tile's half rows and half columns inside the
    // frame (uint32); kNearOn (1 when they are the frame's: the step's mark); the
    // upsample's tensor address; then from word kNearWeightsAt the light step's page
    // of the upsample's weights for the quarter it lights (a tap's 8 rows of 32
    // pixels after another, float32). The tensor: a tile's 4 quarters' pages in turn.
    constexpr uint32_t kHalfTile = 16;
    constexpr uint32_t kNearWords = 3 * kHalfTile * kHalfTile;
    constexpr uint32_t kNearRows = kNearWords;
    constexpr uint32_t kNearCols = kNearWords + 1;
    constexpr uint32_t kNearOn = kNearWords + 2;
    constexpr uint32_t kNearUpsample = kNearWords + 3;
    constexpr uint32_t kNearPageBytes = 4096;
    constexpr uint32_t kNearTaps = 4;
    constexpr uint32_t kNearQuarters = 4;
    constexpr uint32_t kNearQuarterRows = 32 / kNearQuarters;
    constexpr uint32_t kNearWeightsAt = kNearPageBytes / 4;
    constexpr uint32_t kNearWeightsBytes = 4096;
    constexpr uint32_t kNearPlaneBytes = 8192;
    static_assert(kNearWeightsBytes == 4 * kNearTaps * kNearQuarterRows * 32);
    static_assert(kNearPlaneBytes == kNearPageBytes + kNearWeightsBytes);

    // The rings: half of W_T's record (kNearPartTiles bfp8_b tiles of the record's 8,
    // tile k the half rows 2k and 2k + 1, a half pixel a row), S_T (a bfloat16 tile,
    // its rows W's columns, columns 0 to 2 the channels), E of one record tile (a
    // float32 tile).
    constexpr uint32_t kNearRecordTiles = 8;
    constexpr uint32_t kNearParts = 2;  // the record asked and multiplied in halves
    constexpr uint32_t kNearPartTiles = 4;
    static_assert(kNearPartTiles * kNearParts == kNearRecordTiles);
    constexpr uint32_t kNearWTileBytes = 1088;
    constexpr uint32_t kNearSTileBytes = 2048;
    constexpr uint32_t kNearETileBytes = 4096;

    // The frame word half: the frame's half columns << 16 | its half rows.
    constexpr uint32_t kNearHalfShift = 16;

    // Give-up places (the writer's word): a bad record.
    constexpr uint32_t kWhereNearTileBad = 56;

}  // namespace near_tile_step
