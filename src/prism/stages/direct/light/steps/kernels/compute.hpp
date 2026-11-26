// The light step on the compute CPUs: the pack CPU lights the tile's rows a quarter at
// a time from its surface and visibility planes into the visibility's colour planes
// (the displayed form, or with glass the linear then the glass form); the unpack CPU
// serves its mails; the math CPU has no part.
#pragma once

#include <stdint.h>

#include "../../../../../core/include/compute_mail.hpp"
#include "../../../../../core/include/grid.h"
#include "../../../../../core/include/thread/frame.h"
#include "../../../../../core/include/thread/record.h"
#include "../../kernels/light.h"
#include "../../kernels/from_raster.hpp"
#include "light_step.h"

#if defined(TRISC_PACK)
#include "planes.hpp"
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

    // The request ring pair of the light step's next pass of pages: the two in turn.
    inline uint32_t next_turn() {
        static uint32_t turn = 0;
        turn ^= 1u;
        return turn;
    }

    static_assert(kLightStepProfileWords >= light_k::kLightProfWords);

#if defined(TRISC_PACK)
    static_assert(4 * (kLwField + 1024 * kFieldCorners) <= kLightStepWorkBytes);
    static_assert(4 * (2 * kPagesHashSize + kShadeSlots) <= kLightStepPagesBytes);

    // The form's numbers from the table; false: out of range (given up).
    inline bool form_numbers(
        const compute_mail::Waits& waits,
        const uint32_t* table,
        uint32_t mode,
        LightNumbers& numbers
    ) {
        const uint32_t* shade_table = table + kLightShadeTableAt;
        numbers.terms = table[kLtTerms];
        numbers.lamps = table[kLtLamps];
        numbers.bits = table[kLtExponentBits];
        numbers.graded = table[kLtSaturation] != kOneBits ||
            table[kLtCurve] != kCurvePlain;
        if (numbers.lamps > kLampsMax || numbers.bits > 11 ||
            table[kLtCurve] > kCurveFilmic || mode > kLightGlass ||
            (mode == kLightGlass &&
             kTabMaterial + kMaterialWords * shade_table[kTabMaterials] >
                 kLightShadeTableBytes / 4)) {
            compute_mail::stop(waits.stops, waits.stops.gave_bad, kWhereLightStepBad);
            return false;
        }
        return true;
    }

    // The tile's rows in one form (`mode`: 0 displayed, kLightLinear, kLightGlass)
    // from `from` into the visibility's colour planes. False: gave up.
    template <typename Ctx, typename Tile>
    bool light_form(
        Ctx& ctx,
        const compute_mail::Waits& waits,
        const Tile& tile,
        const FormPlanes& from,
        uint32_t mode
    ) {
        const uint32_t* table = reinterpret_cast<const uint32_t*>(ctx.light_table);
        const bool glass = mode == kLightGlass;
        Pass pass = {waits, 0, 0, table, {table, 0, 0, 0, mode, false}};
        pass.cam = table + kLtCamera;
        pass.glass = glass;
        const uint32_t* material_words = table + kLightShadeTableAt + kTabMaterial;
        if (!form_numbers(waits, table, mode, pass.numbers)) {
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
                ctx.cache + kZeroTexel + kFieldDirectionBytes * direction
            ) = 0;
        }
        pass.pages.place(reinterpret_cast<uint32_t*>(ctx.light_pages));
        uint32_t* work = reinterpret_cast<uint32_t*>(ctx.light_work);
        uint32_t values[kLightStepProfileWords] = {};
        pass.values = values;
        pass.index = work + kLwIndex;
        pass.field_index = work + kLwField;
        pass.slots = reinterpret_cast<const uint32_t*>(ctx.cache);
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
            // this quarter's requests to the ring pair's half whose turn it is
            const uint32_t turn = next_turn();
            pass.ask = ctx.asks[turn];
            pass.done = ctx.dones[turn];
            uint32_t mark = km::wall();
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
            if (!quarter_colour(pass, in_front, keyed, pointed, field)) {
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

    // The light step on a compute CPU (all three call it). False: gave up (recorded).
    template <typename Ctx, typename Tile, typename Planes>
    bool light_compute(Ctx& ctx, const Tile& tile, Planes& planes) {
#if defined(TRISC_PACK)
        return light_pack(ctx, tile, planes);
#else
        static_cast<void>(tile);
        static_cast<void>(planes);
#if defined(TRISC_UNPACK)
        compute_mail::serve_mails(waits_of(ctx.compute.control()));
#else
        static_cast<void>(ctx);
#endif
        return true;
#endif
    }

}  // namespace light_step
