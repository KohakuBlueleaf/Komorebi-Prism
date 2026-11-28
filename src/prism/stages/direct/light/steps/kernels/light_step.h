// The light step of the tile thread: its kept state's sizes and its give-up places.
// Its words are the build's defines (PRISM_TF_LIGHT_*); its kept state the loop's
// places (kKeptLight*).
#pragma once

#include <stdint.h>

namespace light_step {

    // The kept table page: LIGHT's table with the camera in it (light.h
    // kLightTableBytes).
    constexpr uint32_t kLightStepTableBytes = 4096;
    // The pack CPU's texel addresses: four taps' (1,024 words a tap) from word 0, the
    // field's eight corners' from word 8,192 (pack/dst.hpp kLwIndex, kLwField).
    constexpr uint32_t kLightStepWorkBytes = 65536;
    // With the sun map's T: the work's bytes after the field's corners for its taps'
    // texel addresses, then their codes, then its tile's numbers (pack/dst.hpp
    // kLwTransmit, kTransmitAllWords).
    constexpr uint32_t kLightStepTransmitBytes = 16416;
    // A pass's page table (texel_pages Pages: keys, slots, the places used), then its
    // ask list (the pages, from word 1).
    constexpr uint32_t kLightStepPagesBytes = 2560;
    constexpr uint32_t kLightStepAskedBytes = 576;
    // The profile words a tile (light.h kLightProf*).
    constexpr uint32_t kLightStepProfileWords = 25;
    // A form's pass state on the pack CPU (colour.hpp LitPass), then its profile words.
    constexpr uint32_t kLightStepPassBytes = 512;

    // Give-up places (the writer's word): a bad table or record, the unpack CPU's mail,
    // a buffer's front or room, the table's and the camera's reads (begin).
    constexpr uint32_t kWhereLightStepBad = 48;
    constexpr uint32_t kWhereLightStepMail = 49;
    constexpr uint32_t kWhereLightStepRing = 50;
    constexpr uint32_t kWhereLightStepTable = 51;
    constexpr uint32_t kWhereLightStepCamera = 52;

}  // namespace light_step
