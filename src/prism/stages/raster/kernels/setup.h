// The per-triangle passes: COUNT and SETUP over each core's partition of the mesh, 32
// triangles a block; handlers from 11, apart from the fill's (raster.h): one program.
#pragma once

#include <stdint.h>

#include "../../../core/include/grid.h"

// LANES: every block's records as the vector unit leaves them, for the exactness check.
// Each handler's command words: kernels/README.md.
constexpr uint32_t kHandlerLanes = 11;
// COUNT: per core, over its partition, the records of every tile and their rows in it
// (two arrays of kTiles words), and the histograms kept for HIST.
constexpr uint32_t kHandlerCount = 12;
// SETUP: each kept record goes once to every item (a tile, or a band of its rows) it
// reaches, at that item's next slot.
constexpr uint32_t kHandlerSetup = 13;
// HIST (writer only): each core writes, per heavy tile, the 32 counts COUNT kept for it
// (kCbHist).
constexpr uint32_t kHandlerHist = 14;
// PLACE (writer only, bank required): directory pages, end slots and list headers from
// the middle pass's words in the items region.
constexpr uint32_t kHandlerPlace = 15;
// SUM (writer only): the counters' sums over the cores, 16 tiles a slice: each core's
// entries before it per tile into its slots page, the totals for the X280 thread.
constexpr uint32_t kHandlerSum = 16;
// HSUM (writer only): the same for HIST's histograms, one heavy tile at a time: each
// core's counts before it, summed over the groups, into its page at prefixes_address.
constexpr uint32_t kHandlerHsum = 17;
// a8 (grid.h): the bank, whose small arrays are then bank addresses (mesh, lists stay
// tensors); the grid, to whose padded frame COUNT, SETUP and LANES clip the box.

// The tables' tiles: the load's capacity (grid.h); the items, an item a tile and the
// heavy tiles' bands past it (grid.h kBandCapacity).
constexpr uint32_t kTiles = kTileCapacity;
constexpr uint32_t kBandItems = kBandCapacity;
constexpr uint32_t kItems = kTiles + kBandItems;

constexpr uint32_t larger(uint32_t a, uint32_t b) {
    return a > b ? a : b;
}

// COUNT's costs: the range's blocks, then the cost summed after j x blocks / 31, j 1-31
constexpr uint32_t kCostKnots = 31;
// A block's predicted cost: per block, kept triangle or piece, entry, clipped one; a
// fit of SETUP's cycles, whose ranges COUNT shares (README "what was sped up")
constexpr uint32_t kCostBlock = 4050;
constexpr uint32_t kCostKept = 400;
constexpr uint32_t kCostEntry = 40;
constexpr uint32_t kCostClipped = 9250;

// Buffers, apart from the fill's (raster.h) so that one program can hold both.
constexpr uint32_t kCbMesh = 4;    // mesh pages in, the camera's page first
constexpr uint32_t kCbSlots = 5;   // SETUP: the list slot of each item's next record
constexpr uint32_t kCbWork = 6;    // the pack thread's own space
constexpr uint32_t kCbRec = 17;    // record pages out
constexpr uint32_t kCbCount = 18;  // COUNT's counters
constexpr uint32_t kCbOut = 19;    // to the writer: the count, box words, then records
constexpr uint32_t kCbHist = 7;    // COUNT to HIST: per tile 16 uint16 counts of starts
                                   // in each 2-row group, then 16 of ends
constexpr uint32_t kCbItems = 8;   // SETUP's items page
constexpr uint32_t kMeshPages = 4;
constexpr uint32_t kRecPages = 2;
constexpr uint32_t kSlotsBytes = 4 * kItems;  // a word an item
// SETUP's items page: a word a tile, then the items' rows (uint16 each) from kItemRows
constexpr uint32_t kItemsBytes = 4 * kTiles + 2 * kItems;
constexpr uint32_t kItemRows = 4 * kTiles;
// SETUP with kSetupPrefix in list_slots (a6): each core's slots page from the prefixes
// and the items' base words (first slot | 1 + heavy index << kBaseSlotBits).
constexpr uint32_t kSetupPrefix = 0x80000000;
constexpr uint32_t kBaseAt = kItemsBytes;  // 64-byte aligned: kTiles a multiple of 32
static_assert(kBaseAt % 64 == 0);
constexpr uint32_t kBaseSlotBits = 23;
constexpr uint32_t kHprefixAddrAt = kBaseAt + 4 * kItems;
// Shaded SETUP: then the shade tensor (0: none), per mesh block 32 texel areas of the
// albedo, 32 material words, 32 of the normal, 32 of the specular; corners u, v, light.
constexpr uint32_t kShadeAddrAt = kHprefixAddrAt + 4;
constexpr uint32_t kShadeBlockBytes = 512;
// material | the albedo's, normal's, specular's levels << 16, << 20, << 24 (shade.h)
// | the shade block's bit 28 (lit: no tangent frame, shade.h kShadeNoFrame)
constexpr uint32_t kRecShadeWord = 30;
constexpr uint32_t kShadeWordKept = 0x10000000;
constexpr uint32_t kHprefixPageBytes = 128 * kHeavyCapacity;  // 128 B a heavy tile
// SUM's totals' room: the frame's T tiles (16-tile slices) entries, rows from 4 T, then
// HSUM's 128 bytes per heavy tile from 8 T (kSumsHeavyAt at the capacity: the most)
constexpr uint32_t kSumsHeavyAt = 8 * kTiles;
// Then PLACE's words: frame words, per item and per fill core (README.md); each part on
// 64 bytes, as a DRAM read must start (one at 16 mod 64 returned the line's start).
constexpr uint32_t kFrameWordsAt = kHprefixAddrAt + 64;
static_assert(kShadeAddrAt + 4 <= kFrameWordsAt);
constexpr uint32_t kItemWordsAt = kFrameWordsAt + 64;
constexpr uint32_t kItemWords = 2;
constexpr uint32_t kCoreWordsAt = kItemWordsAt + 4 * kItemWords * kItems;
constexpr uint32_t kCoreWords = 4;
constexpr uint32_t kMaxFillCores = 248;
constexpr uint32_t kItemsRegionBytes = kCoreWordsAt + kCoreWords * 4 * kMaxFillCores;
// A camera area in the regions (the areas one after another, kAreaPages pages each):
// page 0 the view's page, the camera's kCamWords numbers at word 0 and the view's words
// at kViewAt (its grid word at kViewGrid, grid.h's a8 bits 4 to 31); then one page a
// core (kMaxFillCores), its block range (first, end) at words 0 and 1 and its costs
// (COUNT's 128 bytes) at kAreaCostsAt.
constexpr uint32_t kAreaPageBytes = 4096;
constexpr uint32_t kAreaPages = 249;
static_assert(kAreaPages == 1 + kMaxFillCores);
constexpr uint32_t kAreaCostsAt = 64;
constexpr uint32_t kViewAt = 64;
constexpr uint32_t kViewGrid = 0;
// The list and directory words PLACE writes, as raster.h's.
constexpr uint32_t kLayDirIds = 3;
constexpr uint32_t kLayDirFrame = 1000;
constexpr uint32_t kLayItemEmpty = 0x80000000;
constexpr uint32_t kLayRow0Shift = 16;
constexpr uint32_t kLayRow1Shift = 22;
constexpr uint32_t kLayMarkTile = 0xFFFFFFFE;
constexpr uint32_t kLayMarkEnd = 0xFFFFFFFF;
constexpr uint32_t kLayHdrTile = 1;
constexpr uint32_t kLayHdrCount = 2;
constexpr uint32_t kLayHdrRow0 = 3;
constexpr uint32_t kLayHdrRow1 = 4;
constexpr uint32_t kCountBytes = 8 * kTiles;  // entries, then rows a tile
constexpr uint32_t kWorkCostsAt = 11776;      // then COUNT's costs, 128 bytes
// then a clipped triangle's polygon (6 corners of 24 bytes)
constexpr uint32_t kWorkPolygonAt = 12288;
constexpr uint32_t kWorkPolygonBytes = 160;
constexpr uint32_t
    kWorkBytes = 12448;  // records of a block, of pieces, crossing corners, the above
static_assert(kWorkBytes == kWorkPolygonAt + kWorkPolygonBytes);
constexpr uint32_t kOutBytes = 4096;
constexpr uint32_t kHeavyBytes = 4096;  // HIST's heavy tiles: at most 1,023
constexpr uint32_t kDirPageBytes = 4096;
// COUNT's histograms, 64 bytes a tile (RASTER_RECOUNT: a heavy tile, README.md); PLACE
// (items region, directory page, slot, headers), SETUP's reader use its space after.
constexpr uint32_t kHeavyMax = kHeavyCapacity;
static_assert(kHeavyMax < kHeavyBytes / 4);  // the heavy page: the count, the tiles
static_assert(kHeavyMax < 1u << (32 - kBaseSlotBits));  // base words: 1 + heavy index
#ifdef RASTER_RECOUNT
constexpr uint32_t kHistTiles = kHeavyMax;
static_assert(2 * kTiles + kHeavyBytes <= 8 * kTiles);  // the map, the list (kCbCount)
#else
constexpr uint32_t kHistTiles = kTiles;
#endif
constexpr uint32_t kHistBytes = (larger(
    64 * kHistTiles,
    larger(
        kItemsRegionBytes + kDirPageBytes + 128 + kOutBytes,
        kHprefixAddrAt - kBaseAt + 64 + kHprefixPageBytes
    )
));
constexpr uint32_t kOutPages = 4;
constexpr uint32_t kOutEntries = 31;
constexpr uint32_t kOutLast = 0x80000000;  // in an out page's count: the last page
// COUNT: box words a page (after the count)
constexpr uint32_t kOutWords = 1023;
constexpr uint32_t kListPageBytes = 2048;
constexpr uint32_t
    kTilesX = 32;  // the default grid's tiles a row (experiments' writers)
constexpr uint32_t kBlockSlots = 18;   // x, y, z of corners 0 to 2, then their colours
constexpr uint32_t kMeshBytes = 2304;  // kBlockSlots vectors of 32 words
constexpr uint32_t kMeshPageBytes = 2816;  // a mesh page: the mesh's block, the shade's
static_assert(kMeshPageBytes == kMeshBytes + kShadeBlockBytes);
constexpr uint32_t kRecBytes = 4096;  // 32 records of 32 words
static_assert(kMeshBytes == kBlockSlots * 32 * 4);
constexpr uint32_t kCamWords = 16;  // the scene's camera (prism_reference.scene)
static_assert(4 * kCamWords <= kViewAt && kViewAt + 64 <= kAreaPageBytes);
static_assert(kAreaCostsAt >= 8 && kAreaCostsAt + 128 <= kAreaPageBytes);

// Record words 24 to 31 as the vector unit leaves them: the box's columns and rows as
// float32 (1.5 x 2^23 + n), the doubled area unordered, the corners' camera distances.
constexpr uint32_t kRawX0 = 24;
constexpr uint32_t kRawX1 = 25;
constexpr uint32_t kRawY0 = 26;
constexpr uint32_t kRawY1 = 27;
constexpr uint32_t kRawArea = 28;
constexpr uint32_t kRawZ = 29;
constexpr uint32_t kMagic = 0x4B400000;  // float32(1.5 x 2^23)

// Waits give up after kWaitCycles (0.8 s) with kGaveWait, where: 1, 2 unpack's mesh
// page, hand-back; 3 pack's next page; 4 unpack's slots or items page.
constexpr uint32_t kWaitCycles = 0x40000000;
constexpr uint32_t kGaveWait = 4;
constexpr uint32_t
    kGaveBadSlot = 5;  // a slot past the lists or the slots page; where: tile
// A kept record whose box leaves the image, or a clipped polygon that is not 3 or 4
// corners, gives up with these codes (where: the low bits of the triangle number).
constexpr uint32_t kGaveBadBox = 6;
constexpr uint32_t kGaveBadClip = 7;
// A histogram count past 65,535 (where: the tile); HIST's heavy tiles past its page or
// out stride (HSUM: past its pages); PLACE without the thread's bank.
constexpr uint32_t kGaveBadHist = 8;
constexpr uint32_t kGaveBadHeavy = 9;
constexpr uint32_t
    kGaveBadPlace = 10;  // PLACE, SUM or HSUM without a bank (where: 0, the handler)

// Profile (profile_address, a9, not 0): 32 words per pass per core, at 128 x (handler -
// kHandlerCount) of its page; the threads leave wall-clock counters, the writer sends.
constexpr uint32_t kCbSProf = 9;
constexpr uint32_t kSProfBytes = 256;
constexpr uint32_t kSProfPageBytes = 4096;
constexpr uint32_t kSProfReader = 0;  // reserve wait, read, total, bytes, start
constexpr uint32_t kSProfPack = 8;  // mail wait, vector, scalar, total, kept, clipped,
                                    // entries, out wait
constexpr uint32_t kSProfWriter = 16;  // wait, write, total, bytes, start, pages
