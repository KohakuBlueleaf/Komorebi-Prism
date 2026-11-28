// The near tile step of the tile thread: its rings, its plane's words and its give-up
// places. Its words are the build's defines (PRISM_TF_NEAR_TILE_*).
#pragma once

#include <stdint.h>

namespace near_tile_step {

    // The plane near.light: E, a channel's kNearSide x kNearSide half pixels (from the
    // tile's corner, row by row: the tile and one more row and column) after another
    // as float32 from word 0; the plane's half rows and half columns inside the frame
    // (uint32); kNearOn (1 when they are the frame's: the step's mark); the upsample's
    // tensor address; kNearSeq (the tile's count on the pack CPU once its table is in);
    // from word kNearWeightsAt, while this step runs, the tile's table (kNearTableAt),
    // then the light step's page of the upsample's weights for the quarter it lights (a
    // tap's 8 rows of 32 pixels after another, float32; the tensor: a tile's 4
    // quarters' pages in turn).
    constexpr uint32_t kHalfTile = 16;
    constexpr uint32_t kNearSide = 17;
    static_assert(kNearSide == kHalfTile + 1);
    constexpr uint32_t kNearWords = 3 * kNearSide * kNearSide;
    constexpr uint32_t kNearRows = kNearWords;
    constexpr uint32_t kNearCols = kNearWords + 1;
    constexpr uint32_t kNearOn = kNearWords + 2;
    constexpr uint32_t kNearUpsample = kNearWords + 3;
    constexpr uint32_t kNearSeq = kNearWords + 4;
    constexpr uint32_t kNearPageBytes = 4096;
    static_assert(4 * (kNearSeq + 1) <= kNearPageBytes);
    constexpr uint32_t kNearTaps = 4;
    constexpr uint32_t kNearQuarters = 4;
    constexpr uint32_t kNearQuarterRows = 32 / kNearQuarters;
    constexpr uint32_t kNearWeightsAt = kNearPageBytes / 4;
    constexpr uint32_t kNearWeightsBytes = 4096;
    constexpr uint32_t kNearTableAt = kNearWeightsAt;
    constexpr uint32_t kNearPlaneBytes = 8192;
    static_assert(kNearWeightsBytes == 4 * kNearTaps * kNearQuarterRows * 32);

    // A tile's table (a page of kNearTableWords): its row blocks' count, then
    // kNearEntryWords a block: its operands (at most kNearMostOperands), the first of
    // its W tiles (an operand's each, consecutive), its operands' tiles (16 bits each,
    // two a word, room for 4), the plane places of its 32 rows (16 bits each,
    // kNearSkip: none; a place may be in several blocks, its E their sum).
    constexpr uint32_t kNearTableWords = 1024;
    constexpr uint32_t kNearTableBytes = 4096;
    static_assert(kNearTableBytes == 4 * kNearTableWords);
    constexpr uint32_t kNearEntryWords = 20;
    constexpr uint32_t kNearEntryPlaces = 4;
    constexpr uint32_t kNearMostOperands = 1;
    constexpr uint32_t kNearSkip = 0xFFFF;
    constexpr uint32_t kNearMostBlocks = 32;  // a tile's W tiles at most (its stride)
    static_assert(kNearEntryPlaces + 16 == kNearEntryWords);
    static_assert(kNearPlaneBytes == 4 * kNearTableAt + kNearTableBytes);
    static_assert(kNearTableBytes == kNearWeightsBytes);

    // The rings: a row block's W (kNearMostOperands bfp8_b tiles, tile k its rows on
    // operand k), its operands S (bfloat16 tiles, their rows W's columns, columns 0 to
    // 2 the channels), E of the block (a float32 tile). W and S are
    // reserved and pushed kNearMostOperands at a time, the block's first ones used.
    constexpr uint32_t kNearWTileBytes = 1088;
    constexpr uint32_t kNearSTileBytes = 2048;
    constexpr uint32_t kNearETileBytes = 4096;

    // The frame word half: the frame's half columns << 16 | its half rows.
    constexpr uint32_t kNearHalfShift = 16;

    // Give-up places (the writer's word): a bad record.
    constexpr uint32_t kWhereNearTileBad = 56;

}  // namespace near_tile_step
