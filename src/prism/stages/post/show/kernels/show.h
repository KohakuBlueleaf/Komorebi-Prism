// SHOW, after FILL: each core writes one page of the display tensor for each tile of
// its directory, 32 x 32 pixels of R, G, B, 255; a band writes only its rows' bytes.
// COPY: plane 0 word for word, a tile (row r, column c of 32 x 32) to page
// first + r across + c of another tensor.
#pragma once

#include <stdint.h>

// The reader's colour planes to the writer: a tile's three planes an item.
constexpr uint32_t kShowPlanes = 3;
constexpr uint32_t kShowPages = 6;  // two items: an item never wraps
constexpr uint32_t kShowPageBytes = 4096;
constexpr uint32_t kShowFirstPlane = 1;  // red, green, blue: the frame's planes 1 to 3
constexpr uint32_t kShowTableWords = 256;
constexpr uint32_t kShowAlpha = 0xFF000000;
// The writer's buckets (convert.hpp), a byte each in the buckets' page: the bits from
// kShowBucketBase (2^-32, the lowest power of two the page holds; under the first
// threshold) to kShowOne (1.0, over the last) in ranges of 2^kShowBucketShift.
constexpr uint32_t kShowBucketBase = 0x2F800000;
constexpr uint32_t kShowOne = 0x3F800000;
constexpr uint32_t kShowBucketShift = 16;
constexpr uint32_t kShowBuckets = (kShowOne - kShowBucketBase) >> kShowBucketShift;
// The writer's scratch pages: two converted pages (one converted while the other is
// sent), the profile's, the buckets'.
constexpr uint32_t kShowOutPages = 2;
constexpr uint32_t kShowProfPage = 2;
constexpr uint32_t kShowBucketsPage = 3;
constexpr uint32_t kShowScratchPages = 4;
static_assert(kShowBuckets <= kShowPageBytes);
// The writer's profile page (64 words): cycles converting, waiting for the planes,
// writing, in all; items, rows converted.
constexpr uint32_t kShowProfBytes = 256;
constexpr uint32_t kShowProfConvert = 0;
constexpr uint32_t kShowProfWait = 1;
constexpr uint32_t kShowProfWrite = 2;
constexpr uint32_t kShowProfTotal = 3;
constexpr uint32_t kShowProfItems = 4;
constexpr uint32_t kShowProfRows = 5;
// the view's (view.h): items converted, passes, pages asked
constexpr uint32_t kShowProfViewItems = 6;
constexpr uint32_t kShowProfViewPasses = 7;
constexpr uint32_t kShowProfViewPages = 8;
// A frame table or item the writer cannot use: its gave-up word, where.
constexpr uint32_t kWhereShowBad = 28;
