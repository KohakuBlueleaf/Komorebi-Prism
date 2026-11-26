// A range's blocks through the vector unit, shared by count and place: the streaming
// mover reads the camera's 64 bytes, then the range's mesh blocks (a shaded layer's
// shade blocks beside them) as a Komorebi stream; compute takes them in order and the
// pack CPU runs the stage-wise pass (passes/pack.hpp) on them, its pages to the
// integer mover. Ctx::Buffers names the rings and kept spaces (kinds.py).
#pragma once

#include <stdint.h>

#include "komorebi/device/km_worker.hpp"
#include "komorebi/device/movement/km_movement.hpp"
#include "frame.hpp"
#if !defined(COMPILE_FOR_TRISC)
#include "../../kernels/common/layouts.hpp"
#include "waits.hpp"
#elif defined(TRISC_PACK)
#include "../../kernels/passes/pack.hpp"
#else
#include "../../kernels/common/layouts.hpp"
#endif

// The mover that streams the blocks (0: mover A, 1: mover B); the other is the integer
// side. A build define of the program, mover A when not given.
#ifndef PRISM_GEO_STREAMER
#define PRISM_GEO_STREAMER 0
#endif

namespace geometry_k {

    constexpr uint32_t kStreamer = PRISM_GEO_STREAMER;
    static_assert(kStreamer == km::kMoverA || kStreamer == km::kMoverB);
    // The streaming mover's pattern: every block its own
    constexpr km::Pattern kBlockPattern = kStreamer == km::kMoverA ? km::kPatternA
                                                                   : km::kPatternB;

    // The rings of a range's blocks: the mesh's pair, the shade's pair.
    template <typename Ctx>
    constexpr km::BufferPair mesh_pair() {
        return {Ctx::Buffers::geo_mesh_a, Ctx::Buffers::geo_mesh_b};
    }

    template <typename Ctx>
    constexpr km::BufferPair shade_pair() {
        return {Ctx::Buffers::geo_shade_a, Ctx::Buffers::geo_shade_b};
    }

    // Whether a span's blocks come with their shade blocks: place on a shaded layer.
    template <typename Words>
    inline bool shaded(const Words& page, const Span& span, bool placing) {
        return placing && layer_word(page, span.layer, TF_L_SHADE) != 0;
    }

#if !defined(COMPILE_FOR_TRISC)

    // The streaming mover: the camera's 64 bytes into its half of the mesh's pair,
    // then the span's mesh blocks (and shade blocks, `with_shade`) as one stream each.
    // False: gave up (recorded).
    template <typename Ctx, bool kShade>
    bool blocks_in(Ctx& ctx, const Span& span, bool with_shade) {
        km::Movement& movement = ctx.movement;
        const auto& page = ctx.frame;
        constexpr km::BufferPair mesh = mesh_pair<Ctx>();
        const uint32_t half = mesh.half(kStreamer);
        if (!room(movement, half, 1, kWhereCamera)) {
            return false;
        }
        noc_async_read(
            dram(bank_word(page[TF_GRID]), page[TF_CAMERA], 0, 0),
            get_write_ptr(half),
            kCameraBytes
        );
        if (!landed(movement, kWhereCameraRead)) {
            return false;
        }
        cb_push_back(half, 1);
        const InterleavedAddrGen<true> blocks = {
            .bank_base_address = layer_word(page, span.layer, TF_L_MESH),
            .page_size = setup_k::kMeshBytes
        };
        const km::Stream mesh_stream(
            km::kMoveRead, blocks, span.first, span.blocks, 1, 1, mesh, kBlockPattern
        );
        if constexpr (kShade) {
            if (with_shade) {
                const InterleavedAddrGen<true> shades = {
                    .bank_base_address = layer_word(page, span.layer, TF_L_SHADE),
                    .page_size = setup_k::kShadeBlockBytes
                };
                const km::Stream shade_stream(
                    km::kMoveRead,
                    shades,
                    span.first,
                    span.blocks,
                    1,
                    1,
                    shade_pair<Ctx>(),
                    kBlockPattern
                );
                return movement.move(mesh_stream, shade_stream);
            }
        }
        static_cast<void>(with_shade);
        return movement.move(mesh_stream);
    }

#else

    // Compute (unpack, math and pack all call it): the camera's page, then each block
    // in the half that holds it (a shaded span's shade block beside it), handed from
    // unpack to pack, which runs the pass `handler` (setup.h kHandlerCount or
    // kHandlerSetup); its pages go to the integer mover, the last one marked.
    template <typename Ctx, bool kShade>
    bool pass_over(Ctx& ctx, const Span& span, uint32_t handler, bool with_shade) {
        km::Compute& compute = ctx.compute;
        constexpr km::BufferPair mesh = mesh_pair<Ctx>();
#if defined(TRISC_PACK)
        setup_k::PackPass pack_pass{compute};
        pack_pass.start(
            handler,
            Ctx::Buffers::geo_out,
            Ctx::Buffers::geo_work,
            Ctx::Buffers::geo_costs,
            span.first,
            span.first + span.blocks,
            ctx.frame[TF_GRID],
            with_shade
        );
#else
        static_cast<void>(handler);
#endif
        for (uint32_t page = 0; page <= span.blocks; ++page) {
            const uint32_t half = page == 0
                ? mesh.half(kStreamer)
                : km::block_half(mesh, kBlockPattern, page - 1);
            uint32_t shade_half = 0;
            bool beside = false;  // a shade block beside the mesh block
            if (!compute.wait_front(half, 1)) {
                return false;
            }
            if constexpr (kShade) {
                if (with_shade && page != 0) {
                    beside = true;
                    shade_half = km::block_half(
                        shade_pair<Ctx>(), kBlockPattern, page - 1
                    );
                    if (!compute.wait_front(shade_half, 1)) {
                        return false;
                    }
                }
            }
#if defined(TRISC_UNPACK)
            compute.hand(
                ckernel::ThreadId::PackThreadId,
                ckernel::get_tile_l1_byte_address(half, 0)
            );
            if (beside) {
                compute.hand(
                    ckernel::ThreadId::PackThreadId,
                    ckernel::get_tile_l1_byte_address(shade_half, 0)
                );
            }
            static_cast<void>(compute.handed(ckernel::ThreadId::PackThreadId));
#elif defined(TRISC_PACK)
            const uint32_t at = compute.handed(ckernel::ThreadId::UnpackThreadId);
            const uint32_t shade_at = beside
                ? compute.handed(ckernel::ThreadId::UnpackThreadId)
                : 0;
            if (page == 0) {
                pack_pass.camera(at);
            } else {
                pack_pass.block(at, shade_at);
            }
            compute.hand(ckernel::ThreadId::UnpackThreadId, 1);  // unpack may free it
#endif
            cb_pop_front(half, 1);
            if (beside) {
                cb_pop_front(shade_half, 1);
            }
        }
#if defined(TRISC_PACK)
        pack_pass.end(Ctx::Buffers::geo_profile);
#endif
        return true;
    }

#endif

}  // namespace geometry_k
