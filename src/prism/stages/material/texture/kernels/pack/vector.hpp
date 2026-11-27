// SHADE's pack thread on the vector unit: its Dst vectors and a record's constants, on
// the shared basics (sfpu.hpp) and the passes' reciprocal.
#pragma once

#include <stdint.h>

#include "../../../../../core/include/sfpu.hpp"
#include "../../../../../core/include/texel_pages/pages.hpp"
#include "../../../../raster/kernels/common/layouts.hpp"
#include "../../../../raster/kernels/passes/triangles.hpp"
#include "../waits.hpp"

namespace shade_k {

    using namespace ckernel;
    using fill_k::kGaveBadItem;
    using fill_k::kGaveWait;
    using fill_k::kHdrCount;
    using fill_k::kHdrRow0;
    using fill_k::kHdrRow1;
    using fill_k::kHdrTile;
    using fill_k::kMarkEnd;
    using fill_k::kOutPageBytes;
    using fill_k::kPlanes;
    using fill_k::kPlaneWords;
    using fill_k::kRecTri;
    using fill_k::kRecY0;
    using fill_k::kRecY1;
    using fill_k::kRowBytes;
    using fill_k::kSlotsPerPage;
    using fill_k::kSlotWords;
    using fill_k::kWaitCycles;
    using setup_k::setup_pass::float_bits;
    using setup_k::setup_pass::order;
    using setup_k::setup_pass::recip;
    using namespace pack_sfpu;

    // Dst vectors: FILL's planes (32 p + r), u rows, v rows, a record's numbers (its
    // slot's uv map last, kConstMap); after the records the albedo's linear rgb rows
    // from kVecAlbedo.
    constexpr uint32_t kVecDepth = 0, kVecRed = 32, kVecGreen = 64, kVecBlue = 96;
    constexpr uint32_t kVecTri = 128;
    constexpr uint32_t kVecS = 160, kVecT = 192, kVecRecord = 224, kVecAlbedo = 160;
    constexpr uint32_t kConstTri = 0, kConstW = 1, kConstWLast = 2, kConstH = 3;
    constexpr uint32_t kConstHLast = 4, kConstAcross = 5, kConstFirst = 6;
    constexpr uint32_t kConstBase = 7;   // red, green, blue
    constexpr uint32_t kConstMask = 10;  // the mask's first page less the albedo's
    constexpr uint32_t kConstMap = 11;   // a b c d e f (kMaterialMaps)
    constexpr uint32_t kRecordNumbers = kConstMap + kMapWords;
    constexpr uint32_t kMinusTwo = 0xC0000000;  // a pixel's triangle once coloured
    constexpr uint32_t kMinusOne = 0xBF800000;  // FILL's triangle of an empty pixel
    static_assert(kVecTri == 32 * (kPlanes - 1));

}  // namespace shade_k
