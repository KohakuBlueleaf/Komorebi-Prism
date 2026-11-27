// A file's view transform on the card (prism_reference.post.view): the cube's pages,
// the view's words and the post step's kept slots.
//
// The cube's pages: bricks of 8 x 8 x 8 nodes stepping 7 cells an axis (a node
// shared by two bricks is in both), a page a brick, brick (x, y, z) at page
// x + across (y + across z); node (r, g, b) of a brick at entry (b 8 + g) 8 + r, an
// entry two words: red | green << 16, then blue (16 bits each, 65,535 the value 1.0).
// A cell's eight corners are in one page.
#pragma once

#include <stdint.h>

constexpr uint32_t kViewPageBytes = 4096;
constexpr uint32_t kViewBrickNodes = 8;
constexpr uint32_t kViewBrickCells = 7;
constexpr uint32_t kViewEntryBytes = 8;
constexpr uint32_t kViewStepG = kViewBrickNodes * kViewEntryBytes;  // a green step
constexpr uint32_t kViewStepB = kViewBrickNodes * kViewStepG;       // a blue step
static_assert(kViewStepB * kViewBrickNodes == kViewPageBytes);
// A cell's brick: (cell kViewSevenths) >> kViewSeventhsShift, cell / 7 for cells up to
// kViewCellsMost (the compute CPUs have no divide).
constexpr uint32_t kViewSevenths = 293;
constexpr uint32_t kViewSeventhsShift = 11;
constexpr uint32_t kViewCellsMost = 684;

// The view's words (two pages, after the thresholds' page in the region
// `show_table`): the words, then the log2 table at word kViewLogAt (kViewLogWords
// floats: log2(1 + i / 1024)).
constexpr uint32_t kViewOn = 0;       // 1: the view converts; 0: the colour as it is
constexpr uint32_t kViewCells = 1;    // the cube's cells an axis (nodes - 1)
constexpr uint32_t kViewAcross = 2;   // bricks an axis
constexpr uint32_t kViewBase = 3;     // the cube's pages: their tensor's bank address
constexpr uint32_t kViewLow = 4;      // float: the log2 range's low end
constexpr uint32_t kViewScale = 5;    // float: cells / (high - low)
constexpr uint32_t kViewFloor = 6;    // float: 2^low, the smallest value taken
constexpr uint32_t kViewCeiling = 7;  // float: 2^high, the largest
constexpr uint32_t kViewMatrix = 8;   // nine floats, row-major
constexpr uint32_t kViewLogBits = 10;
constexpr uint32_t kViewLogAt = 64;
constexpr uint32_t kViewLogWords = (1u << kViewLogBits) + 1;
constexpr uint32_t kViewRegionBytes = 8192;
static_assert(kViewRegionBytes == 2 * kViewPageBytes);
static_assert(4 * (kViewLogAt + kViewLogWords) <= kViewRegionBytes);

// The kept slots (cube pages a pass of a tile holds) and work (a word a pixel: its
// page, then its slot's byte offset).
constexpr uint32_t kViewSlots = 16;
constexpr uint32_t kViewWorkBytes = 4096;
// SHOW's class: the pack CPU's counts (items, passes, pages asked) at this byte of the
// writer's scratch pages (its profile page, past what the profile sends).
constexpr uint32_t kViewCountsByte = 9216;
