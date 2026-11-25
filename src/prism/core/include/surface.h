// The layouts SHADE and LIGHT both read: a texel key's page, the lit frame's material
// word, a surface's planes and its directory's frame words.
#pragma once

#include <stdint.h>

// A texel key: (1 + page) << 10 | texel, a page 32 x 32 texels, RGBA8, rows from the
// top (key 0: no texel).
constexpr uint32_t kTexPageBytes = 4096;

// The lit frame's planes: 1/z (merged), material | kind << 16 | exponent << 20 in the
// triangle's plane (empty: FILL's -1, bit 31 set); planes 1 to 3 are LIGHT's.
constexpr uint32_t kMaterialNone = 0x80000000;
constexpr uint32_t kMaterialKindShift = 16;
constexpr uint32_t kMaterialKindMask = 0xF;
constexpr uint32_t kMaterialExponentShift = 20;
constexpr uint32_t kExponentMax = 2047;  // 11 bits under bit 31
// Its surface planes, two frames like the fill's: a (albedo x base, linear) rgb, normal
// x, y | normal z, visibility, specular rgb (x its texel; 0: no specular term).
constexpr uint32_t kSurfacePlanes = 10;
// The surface's directory page: the first frame's words at kDirFrame, the second's
// here.
constexpr uint32_t kSurfaceSecond = 0;
constexpr uint32_t kSurfaceWords = 32;  // both frames' words (kDirFrameMax + 1 each)
constexpr uint32_t kSurfaceLightTable = 16;    // LIGHT's table tensor
constexpr uint32_t kSurfaceLightProfile = 17;  // LIGHT's profile tensor (0: none)
constexpr uint32_t kSurfaceLightPages = 18;    // LIGHT's pages: shadow map, background
constexpr uint32_t kSurfaceAlbedo = 0;
constexpr uint32_t kSurfaceNormal = 3;
constexpr uint32_t kSurfaceVisibility = 6;
constexpr uint32_t kSurfaceSpecular = 7;
