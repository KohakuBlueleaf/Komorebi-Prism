// A range's blocks through the vector unit, shared by count and place: the streaming
// mover reads the camera's 64 bytes, then the range's mesh blocks (a shaded layer's
// shade blocks beside them) as a Komorebi stream; compute takes them in order and the
// pack CPU runs the stage-wise pass (passes/pack.hpp) on them, its pages to the
// integer mover. Ctx::Buffers names the kind's rings as kinds.py declares them.
#pragma once

#include <stdint.h>

#include "komorebi/device/km_worker.hpp"
#include "../../../../program/frame/kernels/account.hpp"
#include "../../../../program/frame/kernels/context.hpp"
#include "komorebi/device/movement/km_movement.hpp"
#include "cull.hpp"
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
        return {Ctx::Buffers::mesh_a, Ctx::Buffers::mesh_b};
    }

    template <typename Ctx>
    constexpr km::BufferPair shade_pair() {
        return {Ctx::Buffers::shade_a, Ctx::Buffers::shade_b};
    }

    // Whether a range's blocks come with their shade blocks: place on a shaded layer.
    template <typename Words>
    inline bool shaded(
        const Words& page, const prism_frame::Range& range, bool placing
    ) {
        return placing && layer_word(page, range.layer, TF_L_SHADE) != 0;
    }

#if !defined(COMPILE_FOR_TRISC)

    // The streaming mover, the camera's page in its half: the range's box read beside
    // it and tested (a layer with boxes), the cut word written (`cut`), the page
    // pushed. False: gave up (recorded).
    template <typename Ctx>
    bool cut_range(
        Ctx& ctx, const prism_frame::Range& range, uint32_t half, bool& cut
    ) {
        const auto& page = ctx.page;
        volatile tt_l1_ptr uint32_t* camera = km::l1(get_write_ptr(half));
        cut = false;
        const uint32_t boxes = layer_word(page, range.layer, TF_L_BOXES);
        if (boxes != 0) {
            const InterleavedAddrGen<true> box_pages = {
                .bank_base_address = boxes, .page_size = kBoxBytes
            };
            noc_async_read(
                box_pages.get_noc_addr(range.first_block / page[TF_RANGE_BLOCKS]),
                get_write_ptr(half) + kBoxAt,
                kBoxBytes
            );
            if (!landed(ctx.movement, kWhereCameraRead)) {
                return false;
            }
            prism_frame::account_add(ctx, FX_BYTES_OTHER, kBoxBytes);
            invalidate_l1_cache();
            const Grid grid = grid_of(page[TF_GRID]);
            cut = box_outside(camera, camera + kBoxAt / 4, grid.across, grid.down);
        }
        camera[kCutWord] = cut ? 1u : 0u;
        asm volatile("fence" ::: "memory");
        cb_push_back(half, 1);
        return true;
    }

    // The streaming mover: the camera's 64 bytes into its half of the mesh's pair,
    // then, unless the range's box lies outside the view (the page's cut word says
    // which), the range's mesh blocks (and shade blocks, `with_shade`) as one stream
    // each. False: gave up (recorded).
    template <typename Ctx, bool kShade>
    bool blocks_in(Ctx& ctx, const prism_frame::Range& range, bool with_shade) {
        km::Movement& movement = ctx.movement;
        const auto& page = ctx.page;
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
        prism_frame::account_add(ctx, FX_BYTES_OTHER, kCameraBytes);
        bool cut = false;
        if (!cut_range(ctx, range, half, cut)) {
            return false;
        }
        if (cut) {
            return true;
        }
        const InterleavedAddrGen<true> blocks = {
            .bank_base_address = layer_word(page, range.layer, TF_L_MESH),
            .page_size = setup_k::kMeshBytes
        };
        const km::Stream mesh_stream(
            km::kMoveRead,
            blocks,
            range.first_block,
            range.blocks,
            1,
            1,
            mesh,
            kBlockPattern
        );
        if constexpr (kShade) {
            if (with_shade) {
                const InterleavedAddrGen<true> shades = {
                    .bank_base_address = layer_word(page, range.layer, TF_L_SHADE),
                    .page_size = setup_k::kShadeBlockBytes
                };
                const km::Stream shade_stream(
                    km::kMoveRead,
                    shades,
                    range.first_block,
                    range.blocks,
                    1,
                    1,
                    shade_pair<Ctx>(),
                    kBlockPattern
                );
                km::Moved moved = {0, 0};
                const bool ok = movement.move(moved, mesh_stream, shade_stream);
                prism_frame::account_add(
                    ctx, FX_BYTES_MESH, moved.tiles / 2 * setup_k::kMeshBytes
                );
                prism_frame::account_add(
                    ctx, FX_BYTES_SHADE, moved.tiles / 2 * setup_k::kShadeBlockBytes
                );
                return ok;
            }
        }
        static_cast<void>(with_shade);
        km::Moved moved = {0, 0};
        const bool ok = movement.move(moved, mesh_stream);
        prism_frame::account_add(ctx, FX_BYTES_MESH, moved.tiles * setup_k::kMeshBytes);
        return ok;
    }

#else

    // Compute (unpack, math and pack all call it): the camera's page (its cut word told
    // by unpack: no block follows), then each block in the half that holds it (a shaded
    // range's shade block beside it), handed from unpack to pack, which runs the pass
    // `handler` (setup.h kHandlerCount or kHandlerSetup); its pages go to the integer
    // mover, the last one marked. False: gave up (recorded).
    template <typename Ctx, bool kShade>
    bool pass_over(
        Ctx& ctx, const prism_frame::Range& range, uint32_t handler, bool with_shade
    ) {
        km::Compute& compute = ctx.compute;
        constexpr km::BufferPair mesh = mesh_pair<Ctx>();
#if defined(TRISC_PACK)
        setup_k::PackPass pack_pass{compute};
        pack_pass.start(
            handler,
            Ctx::Buffers::out,
            Ctx::Buffers::work,
            Ctx::Buffers::costs,
            range.first_block,
            range.first_block + range.blocks,
            ctx.page[TF_GRID],
            with_shade,
            (ctx.page[TF_VIEW] >> 8) == TV_DEPTH
        );
#else
        static_cast<void>(handler);
#endif
        bool cut = false;  // the camera page's cut word
        for (uint32_t page = 0; page <= range.blocks; ++page) {
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
            const uint32_t at = ckernel::get_tile_l1_byte_address(half, 0);
            compute.hand(ckernel::ThreadId::PackThreadId, at);
            if (page == 0) {
                cut = reinterpret_cast<volatile uint32_t*>(at)[kCutWord] != 0;
                compute.hand(ckernel::ThreadId::PackThreadId, cut);
                compute.hand(ckernel::ThreadId::MathThreadId, cut);
            }
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
                cut = compute.handed(ckernel::ThreadId::UnpackThreadId) != 0;
                pack_pass.camera(at);
            } else {
                pack_pass.block(at, shade_at);
            }
            compute.hand(ckernel::ThreadId::UnpackThreadId, 1);  // unpack may free it
#else
            if (page == 0) {
                cut = compute.handed(ckernel::ThreadId::UnpackThreadId) != 0;
            }
#endif
            cb_pop_front(half, 1);
            if (beside) {
                cb_pop_front(shade_half, 1);
            }
            if (cut) {
                break;  // the range's box outside the view: no block was read
            }
        }
#if defined(TRISC_PACK)
        pack_pass.end(Ctx::Buffers::profile);
#endif
        return true;
    }

#endif

}  // namespace geometry_k
