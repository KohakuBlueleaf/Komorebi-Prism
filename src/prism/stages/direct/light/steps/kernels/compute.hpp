// The light step on the compute CPUs: the pack CPU lights the tile's rows a quarter at
// a time from its surface and visibility planes into the first layer's colour planes
// (the displayed form, or with glass the linear then the glass form), its pages asked
// through the loop's request rings, its pass state in the keep `pass`; the unpack CPU
// serves its mails; the math CPU has no part.
#pragma once

#include <new>
#include <stdint.h>

#include "../../../../../core/include/compute_mail.hpp"
#include "../../../../../core/include/grid.h"
#include "../../../../../core/include/thread/frame.h"
#include "../../../../../core/include/thread/record.h"
#include "../../kernels/from_raster.hpp"
#include "../../kernels/light.h"
#include "light_step.h"

#if defined(TRISC_PACK)
#include "colour.hpp"
#endif

namespace light_step {

    // The step's waits: its give-up places, the compute threads' code and limit.
    inline compute_mail::Waits waits_of(uint32_t control) {
        return {
            {control,
             fill_k::kGaveWait,
             fill_k::kGaveBadItem,
             kWhereLightStepMail,
             kWhereLightStepRing,
             kWhereLightStepBad},
            fill_k::kWaitCycles
        };
    }

    // 1 + the glass layer's index when the tile has entries of it, else 0.
    template <typename Tile>
    inline uint32_t glass_of(const volatile uint32_t* page, const Tile& tile) {
        const uint32_t glass = page[PRISM_TF_LIGHT_GLASS];
        return glass != 0 && glass <= TR_LAYERS && tile.entries[glass - 1] != 0 ? glass
                                                                                : 0;
    }

    // The visibility plane's pages of layer `layer`.
    constexpr uint32_t layer_planes(uint32_t visibility, uint32_t layer) {
        return visibility + layer * fill_k::kPlanes * fill_k::kOutPageBytes;
    }

    static_assert(kLightStepProfileWords >= light_k::kLightProfWords);
    static_assert(kLightStepTableBytes == light_k::kLightTableBytes);

#if defined(TRISC_PACK)
    static_assert(4 * (kLwField + 1024 * kFieldCorners) <= kLightStepWorkBytes);
    static_assert(4 * (2 * kPagesHashSize + kShadeSlots) <= kLightStepPagesBytes);
    static_assert(4 * (1 + kShadeSlots) <= kLightStepAskedBytes);

    // The form's numbers from LIGHT's table and SHADE's (`shade_table`, `shade_words`
    // of it kept); false: out of range (given up).
    inline bool form_numbers(
        const compute_mail::Waits& waits,
        const uint32_t* table,
        const uint32_t* shade_table,
        uint32_t shade_words,
        uint32_t mode,
        LightNumbers& numbers
    ) {
        numbers.terms = table[kLtTerms];
        numbers.lamps = table[kLtLamps];
        numbers.bits = table[kLtExponentBits];
        numbers.graded = table[kLtSaturation] != kOneBits ||
            table[kLtCurve] != kCurvePlain;
        if (numbers.lamps > kLampsMax || numbers.bits > 11 ||
            table[kLtCurve] > kCurveFilmic || mode > kLightGlass ||
            (mode == kLightGlass &&
             kTabMaterial + kMaterialWords * shade_table[kTabMaterials] >
                 shade_words)) {
            compute_mail::stop(waits.stops, waits.stops.gave_bad, kWhereLightStepBad);
            return false;
        }
        return true;
    }

    // The keep `pass`: the form's LitPass, then its profile words.
    constexpr uint32_t kPassValuesAt = (sizeof(LitPass) + 3u) & ~3u;
    static_assert(alignof(LitPass) <= 4);
    static_assert(kPassValuesAt + 4 * kLightStepProfileWords <= kLightStepPassBytes);

    // The tile's rows in one form (`mode`: 0 displayed, kLightLinear, kLightGlass)
    // from `from` into the first layer's colour planes. False: gave up.
    template <typename Ctx, typename Tile>
    bool light_form(
        Ctx& ctx,
        const compute_mail::Waits& waits,
        const Tile& tile,
        const FormPlanes& from,
        uint32_t mode
    ) {
        using namespace prism_frame;
        const uint32_t* table = reinterpret_cast<const uint32_t*>(
            ctx.kept(kKeptLightTable)
        );
        // SHADE's table, the common field frame_table (the lit material step's begin)
        const uint32_t* shade_table = reinterpret_cast<const uint32_t*>(
            compute_mail::write_ptr(kFieldFrameTable)
        );
        // the lit material step's page cache, lent for the light's passes
        const uint32_t cache = ctx.kept(kKeptMaterialLitCache);
        const bool glass = mode == kLightGlass;
        const uint32_t held = ctx.kept(kKeptLightPass);
        LitPass& lit = *new (reinterpret_cast<void*>(held)) LitPass{
            {waits, 0, 0, table, {table, 0, 0, 0, mode, false}},
            {&ctx,
             ctx.page[PRISM_TF_LIGHT_PAGES],
             cache,
             reinterpret_cast<uint32_t*>(
                 ctx.kept(kKeptLightPages) + kLightStepPagesBytes
             )}
        };
        Pass& pass = lit.pass;
        pass.cam = table + kLtCamera;
        pass.glass = glass;
        const uint32_t* material_words = shade_table + kTabMaterial;
        if (!form_numbers(
                waits, table, shade_table, PRISM_FRAME_TABLE_WORDS, mode, pass.numbers
            )) {
            return false;
        }
        const uint32_t first_row = tile.first_row, end_row = tile.end_row;
        if (!(first_row < end_row && end_row <= 32 && tile.tile < kTileCapacity)) {
            compute_mail::stop(waits.stops, waits.stops.gave_bad, kWhereLightStepBad);
            return false;
        }
        const uint32_t terms = pass.numbers.terms;
        const bool keyed = (terms & (kTermShadow | kTermBackground)) != 0;
        const bool pointed = (terms & (kTermLamps | kTermSpecular)) != 0;
        const bool field = (terms & kTermIndirect) != 0;
        pass.page_limit = table[kLtPages];
        // the zero texel of each field direction's place (a key of 0)
        for (uint32_t direction = 0; direction < 6; ++direction) {
            *reinterpret_cast<volatile uint32_t*>(
                cache + kZeroTexel + kFieldDirectionBytes * direction
            ) = 0;
        }
        pass.pages.place(reinterpret_cast<uint32_t*>(ctx.kept(kKeptLightPages)));
        uint32_t* work = reinterpret_cast<uint32_t*>(ctx.kept(kKeptLightWork));
        uint32_t* values = reinterpret_cast<uint32_t*>(held + kPassValuesAt);
        for (uint32_t w = 0; w < kLightStepProfileWords; ++w) {
            values[w] = 0;
        }
        pass.values = values;
        pass.index = work + kLwIndex;
        pass.field_index = work + kLwField;
        pass.slots = reinterpret_cast<const uint32_t*>(cache);
        const size_t vl = __riscv_vsetvl_e32m8(32);
        pass.vl = vl;
        // the lanes' column + 0.5, 1 / f
        for (uint32_t lane = 0; lane < 32; ++lane) {
            window()[word(kLvLane) + 2 * lane] = as_bits(
                static_cast<float>(lane) + 0.5f
            );
        }
        setup_k::setup_pass::order(word(kLvLane) + 62);
        TTI_SFPENCC(3, 0, 0, 10);
        immediate(L0, pass.cam[12]);
        recip(L0, L1, L2, L3, L4, L5);
        store(L1, kLvInvF);
        const uint32_t across = grid_of(ctx.page[TF_GRID]).across;  // grid.h
        const uint32_t tile_x = tile.tile % across;
        pass.tile_y = tile.tile / across;
        TTI_SFPENCC(3, 0, 0, 10);
        load(L0, kLvLane);
        immediate(L1, setup_k::float_bits(32 * tile_x));
        add(L0, L1, L0);
        immediate(L1, pass.cam[13]);
        sub(L0, L1, L0);
        over_focal(L0, L2, L3, L4, pass.cam[12]);
        store(L2, kLvXTerm);
        for (uint32_t quarter = 0; quarter < 32 / kLightRows; ++quarter) {
            const uint32_t row0 = kLightRows * quarter;
            pass.row0 = row0;
            pass.first = first_row > row0 ? first_row : row0;
            pass.end = end_row < row0 + kLightRows ? end_row : row0 + kLightRows;
            if (pass.first >= pass.end) {
                continue;
            }
            const uint32_t mark = km::wall();
            planes_in(from, quarter, vl);
            const bool in_front = glass &&
                glass_planes_in(from, quarter, material_words, vl);
            setup_k::setup_pass::order(
                glass ? word(c_vector(2, kLightRows - 1)) + 62
                      : kQuarterWords * kLvPlanes - 1
            );
            const uint32_t now = km::wall();
            values[kLightProfCopyIn] += now - mark;
            pass.mark = now;
            if (!lit_quarter(lit, in_front, keyed, pointed, field)) {
                return false;
            }
            copy_out(from.opaque, quarter, vl);
        }
        return true;
    }

    // The pack CPU's light step: the tile's form or forms, the unpack CPU's end.
    // False: gave up (recorded).
    template <typename Ctx, typename Tile, typename Planes>
    bool light_pack(Ctx& ctx, const Tile& tile, Planes& planes) {
        const compute_mail::Waits waits = waits_of(ctx.compute.control());
        const uint32_t surface = planes.frame_surface;
        const uint32_t opaque = layer_planes(planes.frame_visibility, 0);
        const uint32_t glass = glass_of(ctx.page, tile);
        setup();
        bool lit = light_form(
            ctx, waits, tile, {surface, opaque, 0, false}, glass ? kLightLinear : 0
        );
        if (lit && glass != 0) {
            lit = light_form(
                ctx,
                waits,
                tile,
                {surface + kSurfacePlanes * kOutPageBytes,
                 opaque,
                 layer_planes(planes.frame_visibility, glass - 1),
                 true},
                kLightGlass
            );
        }
        finish();
        compute_mail::end_mails();
        return lit;
    }
#endif

}  // namespace light_step

// The light step on a compute CPU (all three call it). False: gave up (recorded).
template <typename Ctx, typename Tile, typename Planes>
bool light_compute(Ctx& ctx, const Tile& tile, Planes& planes) {
#if defined(TRISC_PACK)
    return light_step::light_pack(ctx, tile, planes);
#else
    static_cast<void>(tile);
    static_cast<void>(planes);
#if defined(TRISC_UNPACK)
    compute_mail::serve_mails(light_step::waits_of(ctx.compute.control()));
#else
    static_cast<void>(ctx);
#endif
    return true;
#endif
}
