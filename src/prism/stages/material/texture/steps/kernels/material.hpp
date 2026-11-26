// Material, the tile thread's step after visibility, unlit (material_compute: the
// colour into the opaque layer's planes of frame.visibility) or lit
// (material_lit_compute: the frame's words there, the surfaces into frame.surface; in
// a DEPTH view only the masked layer's 1/z merged). Its begin (material_begin,
// material_lit_begin) reads the table and, lit, the camera once a command; then the
// layers in the step's order as its list pass streams them: the pack CPU shades, the
// unpack CPU hands the blocks on and serves the pack CPU's mails (its requests'
// answers), the math CPU waits. The pack CPU's state of the tile is in the keep `run`.
#pragma once

#include <new>
#include <stdint.h>

#include "../../../../raster/steps/kernels/lists.hpp"
#include "order.hpp"
#if !defined(COMPILE_FOR_TRISC)
#include "begin.hpp"
#elif defined(TRISC_PACK)
#include "lit/lit.hpp"
#include "unlit.hpp"
#elif defined(TRISC_UNPACK)
#include "../../kernels/waits.hpp"
#endif

#if !defined(PRISM_TF_MATERIAL_LAYERS) && !defined(PRISM_TF_MATERIAL_LIT_LAYERS)
#error "PRISM_TF_MATERIAL_(LIT_)LAYERS: the material step's words (prism.core)"
#endif

// The step's kept state by its name (kKept<Step><Name>, the loop's generated places).
#if defined(PRISM_TF_MATERIAL_LIT_LAYERS)
#define MATERIAL_KEPT(name) prism_frame::kKeptMaterialLit##name
#else
#define MATERIAL_KEPT(name) prism_frame::kKeptMaterial##name
#endif

#if defined(COMPILE_FOR_TRISC)
namespace material_step {

    // The visibility plane's pages of layer `layer`.
    constexpr uint32_t layer_planes(uint32_t visibility, uint32_t layer) {
        return visibility + layer * fill_k::kPlanes * fill_k::kOutPageBytes;
    }

#if defined(TRISC_PACK)
    // The keep `run` on the pack CPU: the Run, the Order, a layer's ListStream.
    constexpr uint32_t kOrderAt = (sizeof(Run) + 3u) & ~3u;
    constexpr uint32_t kListAt = (kOrderAt + sizeof(Order) + 3u) & ~3u;
    static_assert(alignof(Order) <= 4);
#endif

    // A window of the pack CPU's mails: on pack `body()` then the end of the unpack
    // CPU's service, on unpack the service. False: the body gave up.
    template <typename Ctx, typename Body>
    bool served(const Ctx& ctx, Body body) {
        bool done = true;
#if defined(TRISC_PACK)
        done = body();
        compute_mail::end_mails();
#elif defined(TRISC_UNPACK)
        compute_mail::serve_mails(shade_k::waits_of(ctx.compute.control()));
#endif
        static_cast<void>(ctx);
        static_cast<void>(body);
        return done;
    }

    // Each layer of the step's order with slots in `tile`: on the pack CPU `shade(i,
    // list, entries)` when `use(i)` and `ready` (else the blocks drained), in a window
    // of its mails; on the others the blocks taken. False: gave up.
    template <typename Ctx, typename Tile, typename Use, typename Shade>
    bool each_layer(
        const Ctx& ctx,
        const Tile& tile,
        const Order& order,
        bool ready,
        Use use,
        Shade shade
    ) {
        bool done = true;
        for (uint32_t i = 0; i < order.count; ++i) {
            const uint32_t layer = order.layer[i];
            const uint32_t entries = tile.entries[layer];
            if (entries == 0) {
                continue;
            }
#if defined(TRISC_PACK)
            using Stream = list_step::ListStream<Ctx>;
            static_assert(
                kListAt + sizeof(Stream) <= kRunBytes && alignof(Stream) <= 4
            );
            Stream& list = *new (
                reinterpret_cast<void*>(ctx.kept(MATERIAL_KEPT(Run)) + kListAt)
            ) Stream(ctx, tile.slot[layer], entries);
#else
            list_step::ListStream<Ctx> list(ctx, tile.slot[layer], entries);
#endif
            const bool used = use(i);
#if defined(TRISC_PACK)
            if (used) {
                done = served(ctx, [&] {
                           const bool shaded = !ready || shade(i, list, entries);
                           return list_step::drain_rest(list) && shaded;
                       }) &&
                    done;
            } else {
                done = list_step::drain_rest(list) && done;
            }
#else
            done = list.run() && done;
            if (used) {
                served(ctx, [] { return true; });
            }
#endif
            static_cast<void>(ready);
            static_cast<void>(shade);
        }
        return done && ready;
    }

}  // namespace material_step

// The material step on each compute CPU for `tile`, its words at the places `layers`,
// `textures`; `lit` the lit form. A COLOUR view: unlit, the opaque layer's
// colour, the masked layer's merged into it, the glass layer's blended over it (the
// opaque layer's pages of frame.visibility); lit, each layer's frame words in its own
// pages and its surface in frame.surface (the masked one's taken into the opaque
// one's).
// A DEPTH view (lit only): the masked layer merged into the opaque one. False: gave up.
template <bool lit, typename Ctx, typename Tile, typename Planes>
bool material_step_compute(
    Ctx& ctx,
    const Tile& tile,
    Planes& planes,
    uint32_t layers,
    uint32_t textures
) {
    using namespace material_step;
#if defined(TRISC_PACK)
    const uint32_t held = ctx.kept(MATERIAL_KEPT(Run));
    void* order_at = reinterpret_cast<void*>(held + kOrderAt);
    const Order& order = *new (order_at) Order(ctx.page, ctx.page[layers]);
#else
    const Order order(ctx.page, ctx.page[layers]);
#endif
    const bool depth_view = prism_frame::view_kind(ctx.page) == TV_DEPTH;
    bool ready = true;
#if defined(TRISC_PACK)
    const uint32_t table_at = compute_mail::write_ptr(kFieldFrameTable);
    pack_sfpu::setup();
    Run& run = *new (reinterpret_cast<void*>(held)) Run;
    ready = ready &&
        run.start(
            ctx,
            tile,
            table_at,
            ctx.kept(MATERIAL_KEPT(Work)),
            ctx.kept(MATERIAL_KEPT(Cache)),
            ctx.page[textures]
        );
#else
    static_cast<void>(textures);
#endif
    const bool done = each_layer(
        ctx,
        tile,
        order,
        ready,
        [&](uint32_t i) {
            if (order.opaque == TR_LAYERS && order.role[i] != kOpaque) {
                return false;  // nothing to merge into
            }
            return !depth_view || order.role[i] == kMasked;
        },
        [&](uint32_t i, auto& list, uint32_t entries) {
#if defined(TRISC_PACK)
            const uint32_t visibility = planes.frame_visibility;
#if defined(PRISM_TF_MATERIAL_LIT_LAYERS)
            if constexpr (lit) {
                return lit_layer(
                    list,
                    entries,
                    run,
                    order.role[i],
                    layer_planes(visibility, order.layer[i]),
                    layer_planes(visibility, order.opaque),
                    planes.frame_surface,
                    reinterpret_cast<uint32_t*>(ctx.kept(MATERIAL_KEPT(LitWork))),
                    reinterpret_cast<const float*>(ctx.kept(MATERIAL_KEPT(Camera)))
                );
            } else
#endif
            {
                static_cast<void>(entries);
                return unlit_layer(
                    list,
                    run,
                    order.role[i],
                    order.mode[i],
                    layer_planes(visibility, order.layer[i]),
                    layer_planes(visibility, order.opaque)
                );
            }
#else
            static_cast<void>(i);
            static_cast<void>(list);
            static_cast<void>(entries);
            return true;
#endif
        }
    );
#if defined(TRISC_PACK)
    pack_sfpu::finish();
#else
    static_cast<void>(planes);
#endif
    return done;
}

#if defined(PRISM_TF_MATERIAL_LAYERS)
// The unlit material of `tile` (material_step_compute).
template <typename Ctx, typename Tile, typename Planes>
bool material_compute(Ctx& ctx, const Tile& tile, Planes& planes) {
    return material_step_compute<false>(
        ctx,
        tile,
        planes,
        PRISM_TF_MATERIAL_LAYERS,
        PRISM_TF_MATERIAL_TEXTURES
    );
}
#endif

#if defined(PRISM_TF_MATERIAL_LIT_LAYERS)
// The lit material of `tile` (material_step_compute).
template <typename Ctx, typename Tile, typename Planes>
bool material_lit_compute(Ctx& ctx, const Tile& tile, Planes& planes) {
    return material_step_compute<true>(
        ctx,
        tile,
        planes,
        PRISM_TF_MATERIAL_LIT_LAYERS,
        PRISM_TF_MATERIAL_LIT_TEXTURES
    );
}
#endif
#else  // the data-movement CPUs: the begin

#if defined(PRISM_TF_MATERIAL_LAYERS)
// The unlit material's begin: SHADE's table. False: gave up (recorded).
inline bool material_begin(prism_frame::MoverContext& ctx) {
    return material_step::read_begin(ctx, PRISM_TF_MATERIAL_TABLE, 0);
}
#endif

#if defined(PRISM_TF_MATERIAL_LIT_LAYERS)
// The lit material's begin: SHADE's table, the view's camera into the keep camera.
// False: gave up (recorded).
inline bool material_lit_begin(prism_frame::MoverContext& ctx) {
    return material_step::read_begin(
        ctx, PRISM_TF_MATERIAL_LIT_TABLE, ctx.kept(MATERIAL_KEPT(Camera))
    );
}
#endif
#endif
