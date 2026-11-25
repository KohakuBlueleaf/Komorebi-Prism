// The texel pages' protocol SHADE and LIGHT share: the pack thread asks mover A for the
// pages its keys need, mover A reads them into slots and answers; the sizes of both.
#pragma once

#include <stdint.h>

#include "../surface.h"

// The slots: pages read for a pass of rows, and one more page: the white texel.
constexpr uint32_t kShadeSlots = 128;
// An ask page: word 0 the pages to read (kShadeAskEnd: the command's end), then the
// texture pages, the page for slot i at word 1 + i.
constexpr uint32_t kShadeAskBytes = 1024;
constexpr uint32_t kShadeAskPages = 2;
constexpr uint32_t kShadeAskEnd = 0xFFFFFFFF;
static_assert(4 * (1 + kShadeSlots) <= kShadeAskBytes);
// A done page: no content, one an ask served.
constexpr uint32_t kShadeDoneBytes = 64;
constexpr uint32_t kShadeDonePages = 2;
// The pack thread's table of a pass's pages: (1 + page) -> slot, open addressed.
constexpr uint32_t kPagesHashSize = 256;
// A texel address with the mask's slot: (1 + slot) at this bit (0: the albedo's
// texel has the alpha byte); the texel's place in its page the albedo's.
constexpr uint32_t kMaskSlotShift = 20;
static_assert(kShadeSlots * kTexPageBytes < 1u << kMaskSlotShift);
