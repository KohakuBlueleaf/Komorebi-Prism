// Host-binned rasterizer: handlers, buffers, and the layouts of the lists, the
// directory and the frame that the host and the three kernels share.
#pragma once

#include <stdint.h>

#include "../../../core/include/grid.h"

// FILL: a0 directory_address, a1 lists_address, a3 pages_per_item, a4 profile_address,
// a8 the grid (grid.h). Each core fills its directory's tiles and writes their planes.
constexpr uint32_t kHandlerFill = 1;
// ARITH: the same addresses; items are chunks of arithmetic-check inputs.
constexpr uint32_t kHandlerArith = 2;
// SPIN: a0 cycles of a RISC-V spin on each compute thread; no data. For power only.
constexpr uint32_t kHandlerSpin = 3;

// Buffers: list pages in, directory scratch (reader, writer), output pages out.
constexpr uint32_t kCbIn = 0;
constexpr uint32_t kCbDirReader = 1;
constexpr uint32_t kCbDirWriter = 2;
constexpr uint32_t kCbEmpty = 3;  // the writer's empty tile, kPlanes pages
constexpr uint32_t kCbOut = 16;
constexpr uint32_t kInPageBytes = 2048;
constexpr uint32_t kInPages = 8;
constexpr uint32_t kOutPageBytes = 4096;
constexpr uint32_t kOutPages = 15;  // a multiple of 3 and 5: an item never wraps
constexpr uint32_t kDirBytes = 4096;

// Directory page of a core (32-bit words): first list page, list pages, items, then
// the item ids (tile or chunk numbers).
constexpr uint32_t kDirFirst = 0;
constexpr uint32_t kDirPages = 1;
constexpr uint32_t kDirItems = 2;
constexpr uint32_t kDirIds = 3;
constexpr uint32_t kDirMaxItems = 997;
// The frame is several tensors (each read back on its own): pages per tensor at this
// word, then the tensors' addresses, at most kDirFrameMax.
constexpr uint32_t kDirFrame = 1000;
constexpr uint32_t kDirFrameMax = 15;
// An item id with this bit is an empty tile: the writer stores the empty planes.
constexpr uint32_t kItemEmpty = 0x80000000;
// Item id bits 0 to 15: its slot in the frame; a band of a split tile also holds its
// rows [first_row, end_row) in bits 16 to 21 and 22 to 27 (both 0: every row).
constexpr uint32_t kItemSlot = 0xFFFF;
// (a core's L1 holds far fewer tiles than the 16 bits number: prism.core.capacity)
static_assert(kTileCapacity <= kItemSlot + 1);
constexpr uint32_t kItemRow0Shift = 16;
constexpr uint32_t kItemRow1Shift = 22;
constexpr uint32_t kItemRowMask = 0x3F;
constexpr uint32_t kRowBytes = 128;  // two rows of a plane are 256 contiguous bytes

// A list is a stream of 128-byte slots: a tile header, its triangle records in
// triangle order, the next header, ..., an end slot. Word 0 marks headers and the end.
constexpr uint32_t kSlotWords = 32;
constexpr uint32_t kSlotsPerPage = 16;
constexpr uint32_t kMarkTile = 0xFFFFFFFE;
constexpr uint32_t kMarkEnd = 0xFFFFFFFF;
constexpr uint32_t kHdrTile = 1;   // tile number, ty * TX + tx (grid.h)
constexpr uint32_t kHdrCount = 2;  // records that follow
constexpr uint32_t
    kHdrRow0 = 3;  // the item's rows of the tile: [first_row, end_row), even
constexpr uint32_t kHdrRow1 = 4;  // bounds; 0 and 32 for the whole tile

// Triangle record words (float32 bits unless named int).
constexpr uint32_t kRecA = 0;  // edge k: a at kRecA + k, b at kRecB + k, c at kRecC + k
constexpr uint32_t kRecB = 3;
constexpr uint32_t kRecC = 6;
constexpr uint32_t kRecT = 9;        // edge k inside when e > T: +0, or -0's lower
                                     // neighbour 0x80000001 on a top or left edge
constexpr uint32_t kRecW = 12;       // 1/z plane: px, py, constant coefficients
constexpr uint32_t kRecCol = 15;     // colour channel c: kRecCol + 3 c + (0, 1, 2)
constexpr uint32_t kRecX0 = 24;      // first pixel column of the box, as float16
constexpr uint32_t kRecX1 = 25;      // last pixel column + 1, as float16 (both float32
                                     // in a wide build, grid.h)
constexpr uint32_t kRecY0 = 26;      // first pixel row of the box (int)
constexpr uint32_t kRecY1 = 27;      // last pixel row of the box (int)
constexpr uint32_t kRecTri = 28;     // triangle n: the bits kTriBase + n
constexpr uint32_t kRecWLeast = 29;  // its corners' least 1/z times kHeldLeast and
constexpr uint32_t kRecWMost = 31;   // most times kHeldMost: its drawn 1/z between
constexpr uint32_t kHeldLeast = 0x3F7FFF00;  // 1 - 2^-16
constexpr uint32_t kHeldMost = 0x3F800080;   // 1 + 2^-16
// The bits of the float 1.0: a triangle's word is kTriBase + n, a positive normal
// float.
constexpr uint32_t kTriBase = 0x3F800000;

// Output planes of a tile, one 4096-byte page each, in the order of the Dst window:
// depth (1/z, 0 where empty), red, green, blue, triangle word (kRecTri's; -1 where
// empty).
constexpr uint32_t kPlanes = 5;
constexpr uint32_t kPlaneWords = 1024;

// ARITH chunk: 7 input pages of 512 values (a, b, c, px, py, T, d) and 3 output pages
// holding 6 planes of 512 (a px, b py, sum, e, e > T, e > d).
constexpr uint32_t kArithIn = 7;
constexpr uint32_t kArithOut = 3;
constexpr uint32_t kArithLanes = 512;

// Profile page of a core (profile_address of FILL and ARITH): the pack thread's
// counters from word 0, the reader's at kProfReader, the writer's at kProfWriter.
constexpr uint32_t kProfReader = 32;
constexpr uint32_t kProfWriter = 36;
// Reader counters (wait, read, total, pages) at this word of its directory scratch.
constexpr uint32_t kRdWords = 1016;

// The option RASTER_SPREAD: the reader spreads each record's 21 broadcast numbers over
// the 32 lanes of a tile in kCbSpread, which the unpacker writes into Dst tile 7.
constexpr uint32_t kCbSpread = 10;
constexpr uint32_t kSpreadBytes = 4096;
constexpr uint32_t kSpreadPages = 4;
// The writer spreads every second record: the reader names it in kCbSpreadTask (its L1
// address), the writer's tiles go to kCbSpreadOdd; the unpacker takes the two in turn.
constexpr uint32_t kCbSpreadOdd = 11;
constexpr uint32_t kCbSpreadTask = 12;
constexpr uint32_t kSpreadTaskBytes = 16;
constexpr uint32_t kSpreadTaskPages = 64;
constexpr uint32_t kSpreadVectors = 21;
// Six slots of four row groups: the 21 vectors padded to 24.
constexpr uint32_t kSpreadSlotVectors = 24;
constexpr uint32_t kSpreadDstRow = 448;  // Dst tile 7 in 32-bit rows of 16
// Only a record that covers this many rows of its item or more is spread; the others
// are set up from immediates as without the option.
constexpr int32_t kSpreadRows = 4;
// Counters from kProfSpread: the reader's cycles, waits and records, the writer's
// cycles and records; the pack thread's wait for a landed tile at word kProfLanding.
constexpr uint32_t kProfSpread = 40;
constexpr uint32_t kProfLanding = 11;
constexpr uint32_t kWhereWaitLanding = 26;  // pack thread: a spread tile in Dst
constexpr uint32_t kWhereWaitSpread = 27;   // unpack thread: Dst tile 7 free

// Items are written and read as one contiguous block of pages: the output buffer must
// hold a whole number of every item, and every push and pop on it is a whole item.
static_assert(kOutPages % kPlanes == 0 && kOutPages % kArithOut == 0);
// An item that would run past the buffer's end is not touched: the writer's gave-up
// word gets this code (where: compute's write or the writer's send) and the stop flag.
constexpr uint32_t kGaveBadItem = 3;
constexpr uint32_t kWhereBadOut = 16;
constexpr uint32_t kWhereBadSend = 17;
constexpr uint32_t kWhereBadHeader = 24;  // a tile header's tile or rows out of range
// Was a band (rows of a tile's pages, a part of each page) on a session of islands;
// the writer now puts a band's bytes on either island (km::put_bytes): no longer given.
constexpr uint32_t kWhereBandFar = 25;
// Compute's waits give up after kWaitCycles with kGaveWait in the writer's gave-up
// word; the reader's and writer's NoC waits use the runtime's timeout. Where each is:
constexpr uint32_t kGaveWait = 4;
constexpr uint32_t kWaitCycles = 0x40000000;  // 0.8 s at 1.35 GHz
constexpr uint32_t kWhereWaitList = 18;       // unpack thread: a list page
constexpr uint32_t kWhereWaitDone = 19;  // unpack thread: the pack thread's hand-back
constexpr uint32_t kWhereWaitPage = 20;  // pack thread: the next list page
constexpr uint32_t kWhereWaitOut = 21;   // pack thread: free output pages
constexpr uint32_t kWhereFlush = 22;     // writer: its frame writes sent
constexpr uint32_t kWhereReadDone = 23;  // reader or writer: its reads arrived
