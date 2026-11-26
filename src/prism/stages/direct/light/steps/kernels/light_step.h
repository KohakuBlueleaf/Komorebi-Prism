// The light step of the tile thread: its kept state's sizes and its give-up places.
// Its words are the build's defines (PRISM_TF_LIGHT_*); its keeps, planes and request
// rings the tile thread's context and planes give by name.
#pragma once

#include <stdint.h>

namespace light_step {

    // The pack CPU's texel addresses: four taps' (1,024 words a tap) from word 0, the
    // field's eight corners' from word 8,192 (pack/dst.hpp kLwIndex, kLwField).
    constexpr uint32_t kLightStepWorkBytes = 65536;
    // A pass's page table (texel_pages Pages): keys, slots, the places used.
    constexpr uint32_t kLightStepPagesBytes = 2560;
    // The tone's and the terms' profile words a tile (light.h kLightProf*), on the
    // pack CPU's stack.
    constexpr uint32_t kLightStepProfileWords = 25;

    // Give-up places (the writer's word): a bad table or record, the unpack CPU's mail,
    // a request ring's front or room, the table's and the camera's reads (mover A).
    constexpr uint32_t kWhereLightStepBad = 48;
    constexpr uint32_t kWhereLightStepMail = 49;
    constexpr uint32_t kWhereLightStepRing = 50;
    constexpr uint32_t kWhereLightStepTable = 51;
    constexpr uint32_t kWhereLightStepCamera = 52;

}  // namespace light_step
