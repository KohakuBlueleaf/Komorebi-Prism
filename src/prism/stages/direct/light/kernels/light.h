// LIGHT, after the material stage's SHADE: each core turns its tiles' surface planes
// into the frame's colour planes (prism_reference direct.frame rasterize_lighted).
#pragma once

#include <stdint.h>

#include "../../../material/texture/kernels/shade.h"

namespace light_k {

    // The mode (the command's last word): 0 displayed; kLightLinear C (no exposure, no
    // tone curve: glass next); kLightGlass the glass over C, then exposure and the tone
    // curve everywhere.
    constexpr uint32_t kLightLinear = 1;
    constexpr uint32_t kLightGlass = 2;

    // LIGHT's table (model table.light_table; float32 unless int): per channel c at 16
    // c the sky's terms, ambient, the sun; then the words below, the camera, each lamp.
    constexpr uint32_t kLightTableBytes = 4096;
    constexpr uint32_t kLtChannel = 16;
    constexpr uint32_t kLtSky = 0;  // K0, z z, x x - y y, x y, x z, y z, x, y, z
    constexpr uint32_t kLtSkyTerms = 9;
    constexpr uint32_t kLtAmbient = 9;
    constexpr uint32_t kLtSun = 10;
    constexpr uint32_t kLtSunDirection = 48;
    constexpr uint32_t kLtExposure = 51;
    constexpr uint32_t kLtScale = 52;       // exposure / pi
    constexpr uint32_t kLtBackground = 53;  // FILL's background rgb
    constexpr uint32_t kLtInvPi = 56;
    constexpr uint32_t kLtTerms = 57;         // int: kTerm* bits
    constexpr uint32_t kLtExponentBits = 58;  // int: bits of the largest exponent
    constexpr uint32_t kLtLamps = 59;         // int: lamps
    constexpr uint32_t kLtShadowTexel = 60;   // a shadow texel's world size
    constexpr uint32_t kLtShadowBias = 61;    // as 1/z
    // the background's turn: cosine and sine of -turn (a view direction turned about y)
    constexpr uint32_t kLtTurnCos = 62;
    constexpr uint32_t kLtTurnSin = 63;
    constexpr uint32_t kLtShadowCamera = 64;  // 16 words (the scene's camera layout)
    // a map's pages from the light pages' page first - 1, across a row, side in texels
    constexpr uint32_t kLtShadowFirst = 80;
    constexpr uint32_t kLtShadowAcross = 81;
    constexpr uint32_t kLtShadowSide = 82;
    constexpr uint32_t kLtOctaFirst = 83;
    constexpr uint32_t kLtOctaAcross = 84;
    constexpr uint32_t kLtOctaSide = 85;
    constexpr uint32_t kLtOctaLast = 86;     // side - 1
    constexpr uint32_t kLtOctaChannel = 87;  // int: a channel's key step (pages << 10)
    constexpr uint32_t kLtPages = 88;        // int: the light pages
    constexpr uint32_t kLtReflection = 89;  // the glass's reflection of the environment
    constexpr uint32_t kLtFresnel0 = 90;    // the glass's F0 (0.04)
    constexpr uint32_t kLtFresnelRest = 91;  // 1 - F0
    // the tone step (prism_reference post.tone): saturation (1: none), curve (int)
    constexpr uint32_t kLtSaturation = 92;
    constexpr uint32_t kLtCurve = 93;
    constexpr uint32_t kCurvePlain = 0;  // x / (1 + x)
    constexpr uint32_t
        kCurveFilmic = 1;  // x (2.51 x + 0.03) / (x (2.43 x + 0.59) + 0.14)
    constexpr uint32_t kLtCamera = 96;  // 16 words, mover A's copy of the camera
    constexpr uint32_t kLtLamp = 128;
    // a lamp: position, colour, intensity, radius, 1 / radius, size^2
    constexpr uint32_t kLampWords = 16;
    constexpr uint32_t kLampColour = 3;
    constexpr uint32_t kLampIntensity = 6;
    constexpr uint32_t kLampRadius = 7;
    constexpr uint32_t kLampInvRadius = 8;
    constexpr uint32_t kLampSize2 = 9;
    constexpr uint32_t kLampsMax = 32;
    static_assert(4 * (kLtLamp + kLampWords * kLampsMax) <= kLightTableBytes);
    // Indirect light (kTermIndirect; model field.field_words), floats: the field's
    // grid, its pages (blocks across x, a y layer's blocks, 1 + first light page), the
    // decode
    constexpr uint32_t kLtFieldOrigin = 640;
    constexpr uint32_t kLtFieldShift = 643;    // h / 2
    constexpr uint32_t kLtFieldSpacing = 644;  // h
    constexpr uint32_t kLtFieldInverse = 645;  // 1 / h
    constexpr uint32_t kLtFieldDims = 646;     // voxels a side
    constexpr uint32_t kLtFieldAcross = 649;
    constexpr uint32_t kLtFieldLayer = 650;
    constexpr uint32_t kLtFieldFirst = 651;
    constexpr uint32_t kLtFieldUnit = 652;   // a channel: (1 / max code)^2 x the scale
    constexpr uint32_t kLtFieldScale = 655;  // the scale (the host's record)
    constexpr uint32_t kLtFieldPages = 656;  // int: the field's pages
    static_assert(kLtFieldOrigin >= kLtLamp + kLampWords * kLampsMax);
    static_assert(4 * (kLtFieldPages + 1) <= kLightTableBytes);
    // A field page: 8 x 2 x 8 voxels (x, y, z), texel d 128 + (y 8 + z) 8 + x, d +x -x
    // +y -y +z -z; blocks in x, z, y. Texel: bit 31 data, r 20-30, g 9-19, b 0-8.
    constexpr uint32_t kFieldBlockX = 8;
    constexpr uint32_t kFieldBlockY = 2;
    constexpr uint32_t kFieldBlockZ = 8;
    constexpr uint32_t kFieldDirectionTexels = 128;
    static_assert(kFieldBlockX * kFieldBlockY * kFieldBlockZ == kFieldDirectionTexels);
    static_assert(6 * kFieldDirectionTexels * 4 <= kTexPageBytes);
    // The terms past the ones always on (sky, ambient, the sun): its shadow, the lamps,
    // the specular term, the background map (without: FILL's background), the field.
    constexpr uint32_t kTermShadow = 1;
    constexpr uint32_t kTermLamps = 2;
    constexpr uint32_t kTermSpecular = 4;
    constexpr uint32_t kTermBackground = 8;
    constexpr uint32_t kTermIndirect = 16;

    // An item on mover A's way to compute: its word (first_row | end_row << 8,
    // kLightEnd: the command's end; then its tile) and its planes: the surface's ten,
    // the frame's 1/z, material word, in three parts of five pages.
    constexpr uint32_t kLightEnd = 0xFFFFFFFF;
    constexpr uint32_t kLightItemWords = 16;  // an item word's page: 64 bytes
    constexpr uint32_t kLightItemSlots = 8;   // item words in flight
    constexpr uint32_t kLightItemPlanes = 12;
    constexpr uint32_t kLightItemPages = 15;
    // kLightGlass: the glass layer's twelve planes, the opaque frame's C and merged
    // 1/z, in four parts of five pages (the ring's whole size)
    constexpr uint32_t kLightGlassPlanes = 16;
    constexpr uint32_t kLightGlassC = 12;
    constexpr uint32_t kLightGlassDepth = 15;
    constexpr uint32_t kLightGlassPages = 20;
    constexpr uint32_t kLightPart = 5;  // pages pushed and popped at a time: none wraps
    static_assert(kLightItemPages % kLightPart == 0);
    static_assert(kLightGlassPages % kLightPart == 0);
    static_assert(kLightItemPlanes <= kLightItemPages);
    static_assert(kLightGlassPlanes <= kLightGlassPages);
    // The table's page, SHADE's table's size: LIGHT's table, then (kLightGlass) the
    // first words of SHADE's (counts and materials; they must end before its end).
    constexpr uint32_t kLightShadeTableAt = kLightTableBytes / 4;
    constexpr uint32_t kLightShadeTableBytes = kShadeTableBytes - kLightTableBytes;
    // An item out: the frame's five pages, the colour in planes 1 to 3; the ring holds
    // three items.
    constexpr uint32_t kLightOutPages = 5;
    constexpr uint32_t kLightOutItems = 3;
    constexpr uint32_t kLightFirstPlane = 1;  // red; green, blue after it
    constexpr uint32_t kLightColourPlanes = 3;
    // The pack thread's space: per tap the texel addresses (1,024 words a tap) from
    // kLwIndex, the field's corners' from kLwField (pack/layout.hpp).
    constexpr uint32_t kLightWorkBytes = 102400;
    constexpr uint32_t kLwIndex = 0;
    // the lit space's other words: per pixel its slot's byte offset (64 a slot), a
    // row's albedo, normal, specular, mask keys, the winners' table (tri bits + 1 ->
    // slot), a winner's slot, then the empty pixels'
    constexpr uint32_t kLwSlot = 3072;
    constexpr uint32_t kLwRow = 4096;
    constexpr uint32_t kLwHashSize = 2048;
    constexpr uint32_t kLwHashKeys = 4224;
    constexpr uint32_t kLwHashSlots = 6272;
    constexpr uint32_t kLwSlots = 8320;
    // a slot: material word, lit base rgb, specular rgb, tangent, bitangent, normal
    constexpr uint32_t kLitSlotWords = 16;
    constexpr uint32_t kLitSlotEmpty = 1024;  // the empty pixels' slot
    static_assert(
        4 * (kLwSlots + kLitSlotWords * (kLitSlotEmpty + 1)) <= kLightWorkBytes
    );
    // The page table's space (texel_pages Pages): its keys from this word.
    constexpr uint32_t kLightPagesBytes = 8192;
    constexpr uint32_t kLightPagesAt = 1024;

    // The profile page (64 words) of a core: tiles, rows, then cycles waiting for
    // planes, copying in, the vector unit's arithmetic, copying out, the texel steps;
    // pages, passes; in all.
    constexpr uint32_t kLightProfBytes = 256;
    constexpr uint32_t kLightProfTiles = 0;
    constexpr uint32_t kLightProfRows = 1;
    constexpr uint32_t kLightProfWait = 2;
    constexpr uint32_t kLightProfCopyIn = 3;
    constexpr uint32_t kLightProfMath = 4;  // the colour rows but the three below
    constexpr uint32_t kLightProfOut = 5;
    constexpr uint32_t kLightProfKeys = 6;  // the texel keys (shadow, background)
    constexpr uint32_t kLightProfScan = 7;  // pages found, texel addresses
    constexpr uint32_t kLightProfWaitPages = 8;
    constexpr uint32_t kLightProfGather = 9;   // texels to Dst
    constexpr uint32_t kLightProfShadow = 10;  // of kLightProfMath: the shadow's filter
    constexpr uint32_t kLightProfLamps = 11;   // the lamps (their specular terms too)
    constexpr uint32_t kLightProfSpecular = 12;  // the sun's specular term
    constexpr uint32_t kLightProfPages = 13;
    constexpr uint32_t kLightProfPasses = 14;
    constexpr uint32_t kLightProfTotal = 15;
    // not in the total's parts: kLightGlass's quarter tiles with glass in front
    constexpr uint32_t kLightProfGlassQuarters = 16;
    // the field (kTermIndirect), parts of the total: keys, scan, wait, gather, blend;
    // then its pages, passes and the most pages one item read (not summed)
    constexpr uint32_t kLightProfFieldKeys = 17;
    constexpr uint32_t kLightProfFieldScan = 18;
    constexpr uint32_t kLightProfFieldWait = 19;
    constexpr uint32_t kLightProfFieldGather = 20;
    constexpr uint32_t kLightProfFieldBlend = 21;
    constexpr uint32_t kLightProfFieldPages = 22;
    constexpr uint32_t kLightProfFieldPasses = 23;
    constexpr uint32_t kLightProfFieldItemPages = 24;
    constexpr uint32_t kLightProfWords = 25;
    static_assert(4 * kLightProfWords <= kLightProfBytes);
    // The pack thread's field: its space, then the profile's counters from kLwProfile.
    constexpr uint32_t kLwProfile = 25600;
    constexpr uint32_t kLightPackBytes = 102512;
    static_assert(4 * kLwProfile == kLightWorkBytes);
    static_assert(4 * (kLwProfile + kLightProfWords) <= kLightPackBytes);

    // Gave-up places (the writer's word): a wait of the unpack or pack thread, a bad
    // header or table, the reader's loop.
    constexpr uint32_t kWhereLightMail = 29;
    constexpr uint32_t kWhereLightFront = 30;
    constexpr uint32_t kWhereLightBad = 31;
    constexpr uint32_t kWhereLightReader = 32;

}  // namespace light_k
