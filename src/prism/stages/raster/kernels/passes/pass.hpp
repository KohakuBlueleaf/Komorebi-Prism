// The pack thread's pass over a core's blocks: the out pages to the writer (box
// words, records), and each finished block's kept and clipped triangles.
#pragma once

#include <stdint.h>

#include "../common/give_up.hpp"
#include "clip.hpp"
#include "shaded.hpp"
#include "triangles.hpp"

namespace setup_k {

    // Piece `lane`'s held 1/z bounds (raster.h kRecWLeast, kRecWMost) from
    // the screen slots the vector unit left (1/z beyond the near distance: positive).
    inline void piece_depths(uint32_t* words, uint32_t lane) {
        const volatile uint32_t* window = setup_pass::window();
        float least = 0.0f, most = 0.0f;
        for (uint32_t corner = 0; corner < 3; ++corner) {
            const float depth = value(
                window
                    [setup_pass::word(setup_pass::kSlotScreen + 3 * corner + 2) +
                     2 * lane]
            );
            least = corner == 0 || depth < least ? depth : least;
            most = corner == 0 || depth > most ? depth : most;
        }
        words[fill_k::kRecWLeast] = bits(fmul(least, value(fill_k::kHeldLeast)));
        words[fill_k::kRecWMost] = bits(fmul(most, value(fill_k::kHeldMost)));
    }

    // The out pages to the writer: SETUP up to kOutEntries records, each with its box
    // word; COUNT up to kOutWords box words.
    struct Out {
        uint32_t cb;  // the out buffer
        uint32_t* page = nullptr;
        uint32_t filled = 0;
        uint32_t wait = 0;     // cycles waiting for a free out page
        uint32_t entries = 0;  // records sent

        bool open(const km::Compute& compute) {
            if (page == nullptr) {
                const uint32_t asked = km::wall();
                const bool reserved = compute.reserve_back(cb, 1);
                wait += km::wall() - asked;
                if (!reserved) {
                    return false;
                }
                page = cb_ptr(cb);
                filled = 0;
            }
            return true;
        }

        bool add(const km::Compute& compute, const uint32_t* record, uint32_t slot) {
            if (!open(compute)) {
                return false;
            }
            uint32_t* destination = page + 32 * (1 + filled);
#if defined(__riscv_vector)
            const size_t vector_length = __riscv_vsetvl_e32m8(32);
            __riscv_vse32_v_u32m8(
                destination, __riscv_vle32_v_u32m8(record, vector_length), vector_length
            );
            asm volatile("" ::: "memory");
#else
            for (uint32_t word = 0; word < 32; ++word) {
                destination[word] = record[word];
            }
#endif
            page[1 + filled] = slot;
            ++entries;
            if (++filled == kOutEntries) {
                push(false);
            }
            return true;
        }

#ifdef RASTER_WIDE
        // COUNT, wide: a box in three words, up to kOutWords a page.
        bool add_words(
            const km::Compute& compute, uint32_t columns, uint32_t first, uint32_t last
        ) {
            if (!open(compute)) {
                return false;
            }
            page[1 + filled] = columns;
            page[2 + filled] = first;
            page[3 + filled] = last;
            ++entries;
            filled += 3;
            if (filled + 3 > kOutWords) {
                push(false);
            }
            return true;
        }
#endif

        // COUNT: one box word, up to kOutWords a page.
        bool add_word(const km::Compute& compute, uint32_t box_word) {
            if (!open(compute)) {
                return false;
            }
            page[1 + filled] = box_word;
            ++entries;
            if (++filled == kOutWords) {
                push(false);
            }
            return true;
        }

        void push(bool last) {
            page[0] = filled | (last ? kOutLast : 0);
            asm volatile("fence" ::: "memory");
            const uint32_t last_word = reinterpret_cast<volatile uint32_t*>(page)[0];
            asm volatile("and x0, x0, %0" : : "r"(last_word) : "memory");
            cb_push_back(cb, 1);
            page = nullptr;
        }

        // The last page (possibly without entries) tells the writer to stop.
        bool end(const km::Compute& compute) {
            if (!open(compute)) {
                return false;
            }
            push(true);
            return true;
        }
    };

    // One pass's state: the mode and the out pages to the writer.
    struct Pass {
        const km::Compute& compute;
        uint32_t handler;
        Out out;
        bool succeeded = true;
        bool weighted = false;  // SETUP on a shaded frame: a shade block a block
        Grid grid = {kGridDefault, kGridDefault};  // the frame's (a8, grid.h)
        bool depth_view = false;    // a DEPTH view: its 1/z planes from depth_origin
        uint32_t depth_origin = 0;  // 1 / the camera's near distance (bits), else 0
        uint32_t kept_count = 0, clipped = 0;  // the profile's counts
        uint32_t
            block_cost = 0;  // COUNT: the block's predicted cost (setup.h kCostBlock)
        // COUNT with ranges: the costs summed after j x blocks / kCostKnots blocks
        uint32_t* knots = nullptr;
        uint32_t blocks = 0, block = 0, next_knot = 1, cost_sum = 0;

        // knot j once j x blocks / kCostKnots (rounded down) blocks are summed
        void advance() {
            while (
                next_knot <= kCostKnots &&
                next_knot * blocks <= kCostKnots * block + kCostKnots - 1
            ) {
                knots[next_knot++] = cost_sum;
            }
        }

        // Whether `box` is inside the frame's grid.
        static bool inside(const Box& box, Grid grid) {
            return box.first_column >= 0 && box.first_row >= 0 &&
                box.last_column < static_cast<int32_t>(32 * grid.across) &&
                box.last_row < static_cast<int32_t>(32 * grid.down);
        }

        // COUNT: a kept record's predicted cost (setup.h kCostKept, kCostEntry).
        static uint32_t box_cost(const Box& box) {
            return kCostKept +
                kCostEntry * ((box.last_column >> 5) - (box.first_column >> 5) + 1) *
                ((box.last_row >> 5) - (box.first_row >> 5) + 1);
        }

        // The record `words` with its box to `writer`: the writer counts it (COUNT)
        // or sends it to its items (SETUP): narrow, one word (grid.h); wide, COUNT's
        // three words, SETUP's the record. False: the writer's page never came.
        [[gnu::always_inline]] static bool hand(
            Out& writer,
            const km::Compute& compute,
            uint32_t handler,
            const uint32_t* words,
            const Box& box
        ) {
#ifdef RASTER_WIDE
            return handler == kHandlerCount
                ? writer.add_words(
                      compute,
                      static_cast<uint32_t>(box.first_column >> 5) |
                          static_cast<uint32_t>(box.last_column >> 5) << 16,
                      static_cast<uint32_t>(box.first_row),
                      static_cast<uint32_t>(box.last_row)
                  )
                : writer.add(compute, words, 0);
#else
            const uint32_t box_word =
                (static_cast<uint32_t>(box.first_column >> 5) |
                 static_cast<uint32_t>(box.last_column >> 5) << 6 |
                 static_cast<uint32_t>(box.first_row) << 12 |
                 static_cast<uint32_t>(box.last_row) << 22);
            return handler == kHandlerCount ? writer.add_word(compute, box_word)
                                            : writer.add(compute, words, box_word);
#endif
        }

        // A finished record that touches `box` (inside the image, or a give-up); COUNT
        // reads no word of it.
        [[gnu::noinline]] void record(
            const uint32_t* words, const Box& box, uint32_t triangle
        ) {
            if (!inside(box, grid)) {
                give_up(compute.control(), kGaveBadBox, triangle & 0xFFFF);
                succeeded = false;
                return;
            }
            if (knots != nullptr) {
                block_cost += box_cost(box);
            }
            const bool handed = hand(out, compute, handler, words, box);
            succeeded = succeeded && handed;
        }

        // Clips a crossing triangle and sends its pieces (one or two) through the
        // vector unit; their records go out as the triangle's. `records`: free space.
        // `poly`: room for 6 corners (at most 4; 6 so the check below comes first).
        void pieces(
            const Corner* corners,
            float near,
            uint32_t* records,
            Corner* poly,
            uint32_t triangle,
            const uint32_t* shade_words
        ) {
            const uint32_t polygon_size = clip(corners, near, poly);
            if (polygon_size < 3 || polygon_size > 4) {
                give_up(compute.control(), kGaveBadClip, triangle & 0xFFFF);
                succeeded = false;
                return;
            }
            const uint32_t piece_count = polygon_size - 2;
            ++clipped;
            volatile uint32_t* window = setup_pass::window();
            for (uint32_t j = 0; j < piece_count; ++j) {
                for (uint32_t vertex = 0; vertex < 3; ++vertex) {
                    // the fan's piece j: corners 0, j + 1, j + 2
                    const Corner& corner = poly[vertex == 0 ? 0 : vertex + j];
                    for (uint32_t i = 0; i < 3; ++i) {
                        window
                            [setup_pass::word(
                                 setup_pass::kSlotCameraSpace + 3 * vertex + i
                             ) +
                             2 * j] = bits(corner.values[i]);
                        window
                            [setup_pass::word(
                                 setup_pass::kSlotColour + 3 * vertex + i
                             ) +
                             2 * j] = bits(corner.values[3 + i]);
                    }
                }
            }
            setup_pass::order(
                setup_pass::word(setup_pass::kSlotColour + 8) + 2 * (piece_count - 1)
            );
            setup_pass::triangles(
                handler == kHandlerSetup, grid, weighted, depth_origin
            );
            ckernel::tensix_sync();
            setup_pass::records_out(records);
            for (uint32_t j = 0; j < piece_count; ++j) {
                piece_depths(records + 32 * j, j);
            }
            const volatile uint32_t* areas =
                (setup_pass::window() + setup_pass::word(setup_pass::kSlotArea));
            for (uint32_t j = 0; j < piece_count && succeeded; ++j) {
                uint32_t* words = records + 32 * j;
                const Box box = box_of(words);
                if (!kept(words, box)) {
                    continue;
                }
                finish(words, box, triangle);
                if (weighted) {
                    words[kRecShadeWord] = shade_word(areas[2 * j], shade_words);
                }
                ++kept_count;
                record(words, box, triangle);
            }
        }

        // The kept lanes `run` (none crossing): each record (`work`, a lane's 32 words
        // from 0) with its box (`lane_words`: block_finished's pairs) to the writer,
        // the fields it advances in locals.
        [[gnu::noinline]] void kept_out(
            uint32_t run,
            uint32_t* work,
            const uint32_t* lane_words,
            uint32_t first_triangle
        ) {
            const uint32_t* rows = lane_words + 128;
            const km::Compute& core = compute;
            const uint32_t mode = handler;
            const Grid frame_grid = grid;
            const bool costs = knots != nullptr;
            Out writer = out;
            uint32_t kept = kept_count, cost = block_cost;
            bool going = succeeded;
            for (uint32_t left = run; left != 0 && going; left &= left - 1) {
                const uint32_t lane = __builtin_ctz(left);
                const Box box{
                    static_cast<int32_t>(lane_words[2 * lane + 1]),
                    static_cast<int32_t>(lane_words[64 + 2 * lane]),
                    static_cast<int32_t>(rows[2 * lane]),
                    static_cast<int32_t>(rows[2 * lane + 1])
                };
                ++kept;
                if (!inside(box, frame_grid)) {
                    give_up(
                        core.control(), kGaveBadBox, (first_triangle + lane) & 0xFFFF
                    );
                    going = false;
                    break;
                }
                if (costs) {
                    cost += box_cost(box);
                }
                going = hand(writer, core, mode, work + 32 * lane, box);
            }
            out = writer;
            kept_count = kept;
            block_cost = cost;
            succeeded = going;
        }

        // The same after finish_lanes. `work`: records from 0, pieces' records from
        // 1,024, corners from 2,048, the lanes' flags and boxes from 2,688, a clipped
        // polygon at kWorkPolygonAt (bytes); `shade`
        // the block's shade words (weighted).
        void block_finished(
            const uint32_t* mesh,
            uint32_t* work,
            uint32_t first_triangle,
            const uint32_t* shade = nullptr
        ) {
            // pair-major (setup_pass::pairs_out): flags with first columns, last
            // columns with lane numbers, then first with last rows
            uint32_t* lane_words = work + 2688;
            setup_pass::pairs_out(setup_pass::kSlotFlags, 2, lane_words);
            setup_pass::pairs_out(
                setup_pass::kSlotRecords + kRawY0, 1, lane_words + 128
            );
            uint32_t kept_lanes = 0, crossing = 0;
            for (uint32_t lane = 0; lane < 32; ++lane) {
                const uint32_t flags = lane_words[2 * lane];
                kept_lanes |= (flags & 1) << lane;
                crossing |= (flags >> 1 & 1) << lane;
            }
            // SETUP: each kept lane's record by segment loads from the window,
            // before any clipping reuses the window
            if (handler == kHandlerSetup) {
                for (uint32_t left = kept_lanes; left != 0; left &= left - 1) {
                    const uint32_t lane = __builtin_ctz(left);
                    setup_pass::lane_record(
                        const_cast<const uint32_t*>(
                            setup_pass::window() +
                            setup_pass::word(setup_pass::kSlotRecords)
                        ),
                        lane,
                        work + 32 * lane
                    );
                }
            }
            // a shaded frame: each kept record's material and level, before any
            // clipping reuses the window
            if (handler == kHandlerSetup && weighted) {
                const volatile uint32_t* areas =
                    (setup_pass::window() + setup_pass::word(setup_pass::kSlotArea));
                for (uint32_t left = kept_lanes; left != 0; left &= left - 1) {
                    const uint32_t lane = __builtin_ctz(left);
                    work[32 * lane + kRecShadeWord] = shade_word(
                        areas[2 * lane], shade + lane
                    );
                }
            }
            const uint32_t near = (setup_pass::window()[setup_pass::word(
                setup_pass::kSlotCamera + 15
            )]);
            Corner* corners = reinterpret_cast<Corner*>(work + 2048);
            for (uint32_t left = crossing; left != 0; left &= left - 1) {
                const uint32_t lane = __builtin_ctz(left);
                for (uint32_t vertex = 0; vertex < 3; ++vertex) {
                    Corner& corner = corners[3 * lane + vertex];
                    for (uint32_t i = 0; i < 3; ++i) {
                        const uint32_t camera_slot =
                            (setup_pass::word(
                                 setup_pass::kSlotCameraSpace + 3 * vertex + i
                             ) +
                             2 * lane);
                        const uint32_t colour_word =
                            (setup_pass::word(
                                 setup_pass::kSlotColour + 3 * vertex + i
                             ) +
                             2 * lane);
                        corner.values[i] = value(setup_pass::window()[camera_slot]);
                        corner.values[3 + i] = value(mesh[colour_word]);
                    }
                }
            }
            for (
                uint32_t left = kept_lanes | crossing; left != 0 && succeeded;
                left &= left - 1
            ) {
                const uint32_t lane = __builtin_ctz(left);
                if (crossing >> lane & 1) {
                    pieces(
                        corners + 3 * lane,
                        value(near),
                        work + 1024,
                        reinterpret_cast<Corner*>(work + kWorkPolygonAt / 4),
                        first_triangle + lane,
                        shade + lane
                    );
                    continue;
                }
                // the kept lanes before the next crossing one, in lane order
                const uint32_t next_crossing = crossing & left;
                const uint32_t run =
                    (next_crossing == 0
                         ? left
                         : left & ((next_crossing & -next_crossing) - 1));
                kept_out(run, work, lane_words, first_triangle);
                left &= ~run | (run & -run);
            }
            // COUNT: the block's cost, for the next frame's ranges
            if (knots != nullptr) {
                cost_sum +=
                    (block_cost + kCostBlock +
                     kCostClipped *
                         static_cast<uint32_t>(__builtin_popcount(crossing)));
                ++block;
                advance();
            }
            block_cost = 0;
        }
    };

}  // namespace setup_k
