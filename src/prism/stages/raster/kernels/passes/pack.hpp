// COUNT and SETUP on the pack thread: the camera's page into every lane, each block
// through the vector unit and the pass, then the profile, the costs and the last page.
#pragma once

#include <stdint.h>

#include "komorebi/device/km_worker.hpp"
#include "pass.hpp"

namespace setup_k {

    // COUNT's and SETUP's pass on the pack thread, page by page as the lines hand
    // them over: the camera's page, then each mesh block of the core's range.
    struct PackPass {
        Pass pass;
        uint32_t* work = nullptr;
        uint32_t first_block = 0, page = 0;
        uint32_t started = km::wall(), last = 0;
        uint32_t mail = 0, vector_cycles = 0, scalar_cycles = 0;

        explicit PackPass(const km::Compute& compute) : pass{compute, 0, Out{0}} {
        }

        // The command's pass: its handler, buffers (COUNT's costs: `costs`, put by
        // mover B after the last page), range [first, end), grid (a8) and whether a
        // shade block comes with each block (SETUP on a shaded frame).
        void start(
            uint32_t handler,
            uint32_t out,
            uint32_t work_buffer,
            uint32_t costs,
            uint32_t first,
            uint32_t end,
            uint32_t grid,
            bool weighted = false
        ) {
            setup_pass::setup();
            pass.weighted = weighted;
            pass.handler = handler;
            pass.out.cb = out;
            work = cb_ptr(work_buffer);
            first_block = first;
            pass.grid = grid_of(grid);
#ifndef RASTER_WIDE
            if (pass.grid.across > kNarrowAcross || pass.grid.down > kNarrowDown) {
                pass.grid = {kGridDefault, kGridDefault};  // never: refused before
            }
#endif
            if (handler == kHandlerCount) {
                pass.knots = cb_ptr(costs);
                pass.blocks = end - first;
                pass.advance();
            }
            last = km::wall();
        }

        // The camera's page (L1): each number to every lane of its slot, each lane's
        // number as a float for finish_lanes.
        void camera(uint32_t camera_page) {
            mail += km::wall() - last;
            const uint32_t* camera_words = reinterpret_cast<const uint32_t*>(
                camera_page
            );
            asm volatile("fence" ::: "memory");
            for (uint32_t i = 0; i < kCamWords; ++i) {
                setup_pass::fill_slot(setup_pass::kSlotCamera + i, camera_words[i]);
            }
            setup_pass::order(
                setup_pass::word(setup_pass::kSlotCamera + kCamWords - 1) + 62
            );
            const uint32_t lane_numbers = setup_pass::word(setup_pass::kSlotLaneNumber);
            for (uint32_t lane = 0; lane < 32; ++lane) {
                setup_pass::window()[lane_numbers + 2 * lane] = float_bits(lane);
            }
            setup_pass::order(lane_numbers + 62);
            last = km::wall();
        }

        // One mesh block (L1) through the vector unit and the pass; weighted, its
        // shade block (L1) too.
        void block(uint32_t block_page, uint32_t shade_page = 0) {
            const uint32_t vector_started = km::wall();
            mail += vector_started - last;
            if (pass.succeeded) {
                const uint32_t* mesh_words = reinterpret_cast<const uint32_t*>(
                    block_page
                );
                asm volatile("fence" ::: "memory");
                setup_pass::block_in(mesh_words);
                setup_pass::camera_space();
                setup_pass::triangles(
                    pass.handler != kHandlerCount, pass.grid, pass.weighted
                );
                const uint32_t first_triangle = 32 * (first_block + page);
                setup_pass::finish_lanes(
                    pass.handler == kHandlerSetup, float_bits(first_triangle)
                );
                ckernel::tensix_sync();
                const uint32_t scalar_started = km::wall();
                vector_cycles += scalar_started - vector_started;
                pass.block_finished(
                    mesh_words,
                    work,
                    first_triangle,
                    reinterpret_cast<const uint32_t*>(shade_page)
                );
                scalar_cycles += km::wall() - scalar_started;
            }
            ++page;
            last = km::wall();
        }

        // The pack thread's profile words (L1 page `profile_buffer`), the costs' block
        // count, the last out page; the vector unit's state given back.
        void end(uint32_t profile_buffer) {
            volatile uint32_t* profile = cb_ptr(profile_buffer);
            profile[kSProfPack + 0] = mail;
            profile[kSProfPack + 1] = vector_cycles;
            profile[kSProfPack + 2] = scalar_cycles;
            profile[kSProfPack + 3] = km::wall() - started;
            profile[kSProfPack + 4] = pass.kept_count;
            profile[kSProfPack + 5] = pass.clipped;
            profile[kSProfPack + 6] = pass.out.entries;
            profile[kSProfPack + 7] = pass.out.wait;
            asm volatile("fence" ::: "memory");
            if (pass.knots != nullptr) {
                pass.knots[0] = pass.block;  // the blocks summed
                asm volatile("fence" ::: "memory");
            }
            if (pass.succeeded) {
                pass.out.end(pass.compute);
            }
            setup_pass::finish();
        }
    };

}  // namespace setup_k
