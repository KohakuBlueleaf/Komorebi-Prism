// The near tile step of the tile thread: its plane's words and its give-up places.
// Its words are the build's defines (PRISM_TF_NEAR_TILE_*).
#pragma once

#include <stdint.h>

namespace near_tile_step {

    // The plane near.light: a tile's page of the light pages' tensor (a channel's
    // 256 half pixels (16 x 16, row by row) of E after another as float32 from word
    // 0, then the tile's half rows and half columns in the frame, uint32), kNearOn (1
    // when they are the frame's: the step's mark, 0 in the tensor), then from word
    // kNearWeightsAt the tile's page of the upsample's weights (a tap's 1,024 pixels,
    // row by row, after another, float32).
    constexpr uint32_t kHalfTile = 16;
    constexpr uint32_t kNearWords = 3 * kHalfTile * kHalfTile;
    constexpr uint32_t kNearRows = kNearWords;
    constexpr uint32_t kNearCols = kNearWords + 1;
    constexpr uint32_t kNearOn = kNearWords + 2;
    constexpr uint32_t kNearPageBytes = 4096;
    constexpr uint32_t kNearTaps = 4;
    constexpr uint32_t kNearWeightsAt = kNearPageBytes / 4;
    constexpr uint32_t kNearWeightsBytes = 16384;
    constexpr uint32_t kNearPlaneBytes = 20480;
    static_assert(kNearWeightsBytes == 4 * kNearTaps * 1024);
    static_assert(kNearPlaneBytes == kNearPageBytes + kNearWeightsBytes);

    // Give-up places (the writer's word): a bad record.
    constexpr uint32_t kWhereNearTileBad = 56;

}  // namespace near_tile_step
