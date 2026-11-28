// SHADE, between FILL and SHOW on a shaded frame: each core colours its tiles in
// place from materials and textures (prism_reference.raster.frames rasterize_shaded).
#pragma once

#include <stdint.h>

#include "../../../../core/include/surface.h"
#include "../../../../core/include/texel_pages/protocol.h"

// SHADE's words: the directory, the lists, the texture pages, the table, the profile,
// the opaque directory (else 0; the directory and lists the masked or glass layer's),
// the kShade* bits, the grid (its bank: the camera's); lit: the camera's address (0:
// unlit) and the surface directory (merging: the opaque layer's surface).
// The kShade* bits (unlit merging): kShadeMergedDepth also the merged 1/z (plane 0);
// kShadeGlass: tau C + (1 - max tau) colour where nearer (a tie to the surface).
constexpr uint32_t kShadeMergedDepth = 1;
constexpr uint32_t kShadeGlass = 2;
// Lit, a DEPTH view's glass layer (pack/lit/transmit.hpp): its T over the opaque
// layer's 1/z, the codes in the opaque frame's plane 1 (kShadeTransmitRgb: a word a
// texel, else a byte).
constexpr uint32_t kShadeTransmit = 4;
constexpr uint32_t kShadeTransmitRgb = 8;
// With the opaque directory, a pixel nearer than the opaque layer's (a tie to it) with
// alpha byte >= kAlphaOpaque takes the masked colour, else the opaque one, in the
// opaque frame.

// Buffers: the reader's planes, the table, the pack thread's own space; the asks,
// answers and slots are texel_pages' (protocol.h).
constexpr uint32_t kShadePlanePages = 20;  // items of 5, 10 (merging), 15 (LIGHT) pages
// the table in L1: 816 + 37 per material + 2 per (texture, level) words, in steps of
// kShadeTableStepBytes, at least kShadeTableLeastBytes; its bytes the field
// frame_table's, as the build gives them (PRISM_FRAME_TABLE_WORDS)
constexpr uint32_t kShadeTableLeastBytes = 32768;
constexpr uint32_t kShadeTableStepBytes = 4096;
#ifndef PRISM_FRAME_TABLE_WORDS
#error "PRISM_FRAME_TABLE_WORDS: the field frame_table's words (prism.core.fields)"
#endif
constexpr uint32_t kShadeTableBytes = 4 * PRISM_FRAME_TABLE_WORDS;
constexpr uint32_t kShadeWorkBytes = 8192;
constexpr uint32_t kShadeColourPages = 3;  // red, green, blue out
constexpr uint32_t
    kShadeFirstPlane = 1;  // red: the colour planes are the frame's 1 to 3
// An item's pages out: FILL's five (the first three used), so that the ring stays
// where FILL's items expect it and no item wraps (raster.h kOutPages).
constexpr uint32_t kShadeOutPages = 5;

// Table words: counts, texel tables, background, camera; a material: kind | (1 + the
// albedo's level 0 entry, 0: none) << 8, base rgb, ...; an entry: page, w | h << 16.
constexpr uint32_t kTabMaterials = 0;
constexpr uint32_t kTabEntries = 1;
constexpr uint32_t kTabPages = 2;
constexpr uint32_t kTabGamma = 16;        // TEXEL_LINEAR
constexpr uint32_t kTabSigned = 272;      // TEXEL_SIGNED
constexpr uint32_t kTabUnit = 528;        // TEXEL_UNIT
constexpr uint32_t kTabBackground = 784;  // FILL's background rgb
constexpr uint32_t kTabCamera = 800;      // lit: the reader's copy of the camera
constexpr uint32_t kCamWordsShade = 16;   // the scene's camera (prism_reference.scene)
constexpr uint32_t kTabMaterial = 816;
constexpr uint32_t kMaterialWords = 37;
constexpr uint32_t kMaterialMask = 4;      // 1 + mask's entry (sizes the albedo's)
constexpr uint32_t kMaterialNormal = 5;    // 1 + normal's entry
constexpr uint32_t kMaterialSpecular = 6;  // 1 + specular's entry
constexpr uint32_t kMaterialLitBase = 7;   // rgb, emissive: x emissive_scale
constexpr uint32_t kMaterialSpecularColour = 10;  // rgb, 0: no specular term
constexpr uint32_t kMaterialExponent = 13;        // lit: specular exponent (0: none)
constexpr uint32_t kMaterialTau = 14;     // transparent: transmission rgb (else 0)
constexpr uint32_t kMaterialWeight = 17;  // transparent: 1 - max tau (else 1)
// the albedo's (and mask's), normal's and specular's uv maps, each a b c d e f: the
// slot's (u, v) = (a u + b v + c, d u + e v + f) of the stored (u, v)
constexpr uint32_t kMaterialMaps = 18;
constexpr uint32_t kMapWords = 6;
constexpr uint32_t kMapAlbedo = 0;
constexpr uint32_t kMapNormal = 1;
constexpr uint32_t kMapSpecular = 2;
constexpr uint32_t kMaterialNormalScale = 36;  // lit: the normal map's x, y factor
constexpr uint32_t kEntryWords = 2;
// kinds (prism_reference.material.kinds): lit is shaded as textured in this step;
// masked as textured, its holes by the masked layer's SHADE (a6)
constexpr uint32_t kKindFlat = 0;
constexpr uint32_t kKindTextured = 1;
constexpr uint32_t kKindMasked = 2;
constexpr uint32_t kKindLit = 3;
constexpr uint32_t kKindEmissive = 4;
constexpr uint32_t kKindTransparent = 5;  // the glass layer (shaded as textured)
constexpr uint32_t kAlphaOpaque = 128;    // a masked texel under it is a hole

// Record word (SETUP writes it on a shaded frame): material | albedo level << 16 |
// normal level << 20 | specular level << 24.
constexpr uint32_t kRecShade = 30;
constexpr uint32_t kShadeLevelShift = 16;
constexpr uint32_t kShadeNormalLevelShift = 20;
constexpr uint32_t kShadeSpecularLevelShift = 24;
// lit: the triangle's coordinates give no tangent frame (the reference's frame_ok
// false, set by the host): its pixels take the triangle's normal
constexpr uint32_t kShadeNoFrame = 0x10000000;

// A lit item goes out in three parts of kShadeOutPages: the frame's planes (0 and 4
// used), the surface's planes 0 to 4, 5 to 9.
constexpr uint32_t kLitParts = 3;
// The profile page (64 words) of a core: the pack thread's counters.
constexpr uint32_t kShadeProfBytes = 256;
constexpr uint32_t kShadeProfTiles = 0;
constexpr uint32_t kShadeProfRecords = 1;
constexpr uint32_t kShadeProfRows = 2;    // record rows run
constexpr uint32_t kShadeProfPasses = 3;  // passes of rows, each its own pages
constexpr uint32_t kShadeProfPages = 4;   // texture pages read
constexpr uint32_t kShadeProfTexels = 5;  // texels fetched (pixels with a texture)
constexpr uint32_t kShadeProfWaitIn = 6;  // cycles: list pages and planes
constexpr uint32_t kShadeProfCopyIn = 7;  // planes into Dst
constexpr uint32_t kShadeProfDivide = 8;  // u, v, light per pixel
constexpr uint32_t kShadeProfRecord = 9;  // the records' rows
constexpr uint32_t kShadeProfScan = 10;   // pages found, texel addresses
constexpr uint32_t kShadeProfWaitPages = 11;
constexpr uint32_t kShadeProfGather = 12;  // texels and their linear values to Dst
constexpr uint32_t kShadeProfOut = 13;     // colour, planes to the writer
constexpr uint32_t kShadeProfTotal = 14;
// not summed: the most pages one item's rows read, the items read in more than one
// pass
constexpr uint32_t kShadeProfItemPages = 15;
constexpr uint32_t kShadeProfItemPasses = 16;
constexpr uint32_t kShadeProfWords = 17;

// Gave-up places (the writer's word): a wait of the unpack or pack thread, a bad
// header or table, the reader's loop.
constexpr uint32_t kWhereShadeMail = 29;
constexpr uint32_t kWhereShadeFront = 30;
constexpr uint32_t kWhereShadeBad = 31;
constexpr uint32_t kWhereShadeReader = 32;
