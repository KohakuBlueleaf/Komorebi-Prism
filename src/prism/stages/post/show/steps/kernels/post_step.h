// The post step of the tile thread and the DEPTH view's depth_out: their output
// blocks, kept state and give-up places. Their words are the build's defines
// (PRISM_TF_*); their kept state the loop's places (kKept*).
#pragma once

#include <stdint.h>

namespace post_step {

    // A page of a plane, of the display, of a scratch page.
    constexpr uint32_t kPostPageBytes = 4096;
    // An output block: the loop's header (frame.h FO_HEADER_BYTES), then the payload:
    // post's the tile's red, green and blue planes (a band: its rows), depth_out's its
    // 1/z plane.
    constexpr uint32_t kPostHeaderBytes = 16;
    constexpr uint32_t kPostBlockBytes = 12304;
    constexpr uint32_t kDepthBlockBytes = 4112;
    // A data-movement CPU's converted page, both CPUs'.
    constexpr uint32_t kPostScratchBytes = 8192;
    // The thresholds (256 words, show.h kShowTableWords) and their buckets' page.
    constexpr uint32_t kPostTableBytes = 5120;

    static_assert(kPostBlockBytes == kPostHeaderBytes + 3 * kPostPageBytes);
    static_assert(kDepthBlockBytes == kPostHeaderBytes + kPostPageBytes);
    static_assert(kPostScratchBytes == 2 * kPostPageBytes);
    static_assert(kPostTableBytes == 1024 + kPostPageBytes);

    // Give-up places (the writer's word): a display page or band out of range, the
    // thresholds' read; a target page or band out of range.
    constexpr uint32_t kWherePostPage = 54;
    constexpr uint32_t kWherePostTable = 55;
    constexpr uint32_t kWhereDepthPage = 58;

}  // namespace post_step
