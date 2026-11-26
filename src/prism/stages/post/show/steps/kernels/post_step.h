// The post step of the tile thread and the DEPTH view's depth_out: their output
// blocks, kept state and give-up places. Their words are the build's defines
// (PRISM_TF_*); their keeps, planes and output rings the context and planes give.
#pragma once

#include <stdint.h>

namespace post_step {

    // A page of a plane, of the display, of a scratch page.
    constexpr uint32_t kPostPageBytes = 4096;
    // An output block of post: the tile's red, green and blue planes (a band: its
    // rows); of depth_out: its 1/z plane.
    constexpr uint32_t kPostBlockBytes = 12288;
    constexpr uint32_t kDepthBlockBytes = 4096;
    // A data-movement CPU's two converted pages (one converted while the other is
    // written), both CPUs'.
    constexpr uint32_t kPostScratchBytes = 16384;
    // The thresholds (256 words, show.h kShowTableWords) and their buckets' page.
    constexpr uint32_t kPostTableBytes = 5120;

    static_assert(kPostBlockBytes == 3 * kPostPageBytes);
    static_assert(kDepthBlockBytes == kPostPageBytes);
    static_assert(kPostScratchBytes == 2 * 2 * kPostPageBytes);
    static_assert(kPostTableBytes == 1024 + kPostPageBytes);

    // Give-up places (the writer's word): post's output ring, a display page out of
    // range, the thresholds' read, a scratch page's last write; depth_out's ring, a
    // target page out of range, its scratch page's last write.
    constexpr uint32_t kWherePostRing = 53;
    constexpr uint32_t kWherePostPage = 54;
    constexpr uint32_t kWherePostTable = 55;
    constexpr uint32_t kWherePostSent = 56;
    constexpr uint32_t kWhereDepthRing = 57;
    constexpr uint32_t kWhereDepthPage = 58;
    constexpr uint32_t kWhereDepthSent = 59;

}  // namespace post_step
