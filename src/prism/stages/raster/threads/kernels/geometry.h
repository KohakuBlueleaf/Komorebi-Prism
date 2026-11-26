// The geometry thread's layouts: a core's counts, row histograms and positions pages of
// a layer, a band's entry, the sums' scratch, and the codes of their give-ups. Shared
// by the kinds count and place, the sums, and the host (prism.core.headers).
#pragma once

#include <stdint.h>

#include "../../../../core/include/grid.h"
#include "../../../../core/include/thread/frame.h"

#ifndef TR_SLICE_RECORDS
#error "TR_SLICE_RECORDS: the records a slice holds at most (the capacity's)"
#endif
#ifndef RASTER_SLICES
#error "RASTER_SLICES: the slices a view holds at most (the capacity's)"
#endif

namespace geometry_k {

    constexpr uint32_t kSlices = RASTER_SLICES;
    constexpr uint32_t kSliceRecords = TR_SLICE_RECORDS;

    // A core's counts page of a layer: its entries a tile, a word a tile (tile ty TX +
    // tx), 4 x the capacity's tiles.
    constexpr uint32_t kCountTileBytes = 4;
    // A core's row histograms of a layer: a tile's 16 uint16 counts of its entries
    // whose first row is in each 2-row group, then 16 of those whose last row is.
    constexpr uint32_t kHistTileBytes = 64;
    constexpr uint32_t kGroups = 16;
    constexpr uint32_t kTileRows = 32;

    // A core's positions page of a layer (words): slice s's tiles from s x
    // kSliceTilesMost, a word a tile of its run: its first position in the tile's list
    // counted from the slice's place; a cut tile's word kPosCut | its bands <<
    // kPosBandsShift | its first band entry. Band entry e at word kPosTileWords +
    // kBandWords e: its rows (first | end << 8), then the core's first position in the
    // band's list. Slice s's band entries from s x kSliceRecords.
    constexpr uint32_t kPosCut = 0x80000000;
    constexpr uint32_t kPosBandsShift = 24;
    constexpr uint32_t kPosBandsMask = 0x1F;
    constexpr uint32_t kPosEntryMask = 0xFFFFFF;
    constexpr uint32_t kBandWords = 2;
    constexpr uint32_t kBandRowsEndShift = 8;
    // The bands a cut tile has at most (one a 2-row group)
    constexpr uint32_t kBandsMost = 16;

    // The camera's numbers at TF_CAMERA, read whole: 64 bytes on 64
    constexpr uint32_t kCameraBytes = 64;
    // A record (record.h) and a slice's words, one 64-byte line each
    constexpr uint32_t kRecordBytes = 64;
    constexpr uint32_t kSliceBytes = 64;
    // A DRAM read's line: every read here starts and ends on one
    constexpr uint32_t kLine = 64;

    // The sums: the tiles a slice holds at most, and the cores whose words one pass of
    // a mover reads before it waits
    constexpr uint32_t kSliceTilesMost = 32;
    constexpr uint32_t kSumCores = 8;

    // Where each wait of the geometry thread and the sums gives up, and each check of
    // its own (those with km::kGaveBadItem)
    constexpr uint32_t kWhereCamera = 0xC0;      // streaming mover: room for the camera
    constexpr uint32_t kWhereCameraRead = 0xC1;  // streaming mover: the camera read
    constexpr uint32_t kWhereOut = 0xC2;         // integer mover: the pass's next page
    constexpr uint32_t kWhereCountsSent = 0xC3;  // integer mover: a layer written
    constexpr uint32_t kWherePositions = 0xC4;   // integer mover: a layer's positions
    constexpr uint32_t kWhereListsSent = 0xC5;   // integer mover: a page's records out
    constexpr uint32_t kWhereSumRead = 0xC6;     // the sums: cores' words read
    constexpr uint32_t kWhereSumSent = 0xC7;     // the sums: records, words, positions
    constexpr uint32_t kWhereNoPage = 0xC8;      // the sums: the command's block
    constexpr uint32_t kWhereRange = 0xC9;       // a range of no layer, or out of order
    constexpr uint32_t kWhereHist = 0xCA;        // a histogram count past 65,535
    constexpr uint32_t kWhereSlice = 0xCB;       // a slice or a view past the capacity

    static_assert(TR_WORDS * 4 == kRecordBytes, "a record is one line");
    static_assert(TS_WORDS * 4 == kSliceBytes, "a slice's words are one line");
    static_assert(kSlices * kSliceRecords <= kPosEntryMask + 1, "band entries");
    static_assert(kSliceRecords >= kSliceTilesMost, "a slice holds its tiles");
    static_assert(kSliceRecords % 8 == 0, "a slice's band entries on a line");
    static_assert(kSliceTilesMost % 16 == 0, "a slice's tile words on a line");
    static_assert(kBandsMost <= kPosBandsMask, "a cut tile's bands");

    // A core's counts page of a layer, its row histograms page, its positions page
    constexpr uint32_t kCountBytes = kCountTileBytes * kTileCapacity;
    constexpr uint32_t kHistBytes = kHistTileBytes * kTileCapacity;
    constexpr uint32_t kPosTileWords = kSliceTilesMost * kSlices;
    constexpr uint32_t kPositionWords = kPosTileWords +
        kBandWords * kSliceRecords * kSlices;
    constexpr uint32_t kPositionBytes = 4 * kPositionWords;

}  // namespace geometry_k
