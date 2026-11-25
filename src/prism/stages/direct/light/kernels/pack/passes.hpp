// LIGHT on the pack CPU: a command's state the quarter's steps share, and the steps
// run in page passes: the taps' texel addresses and gather, the field's scan and rows.
#pragma once

#include <stdint.h>

#include "../../../../../core/include/texel_pages/passes.hpp"
#include "dst.hpp"
#include "field.hpp"
#include "keys.hpp"
#include "row.hpp"

namespace light_k {

    // A command's state: its buffers' waits, numbers, pages, texel indices and counts;
    // the quarter's rows and the time mark of its steps.
    struct Pass {
        Waits waits;
        uint32_t ask, done;  // the page passes' buffers
        const uint32_t* table;
        LightNumbers numbers;
        const uint32_t* cam;
        bool glass;
        uint32_t page_limit;
        Pages pages;
        uint32_t* index;        // kLightKeys x 1,024 texel addresses
        uint32_t* field_index;  // the field's corners' addresses
        const uint32_t* slots;
        size_t vl;
        uint32_t* values;
        PassCounts counts, field_counts;
        uint32_t tile_y, row0, first, end, mark, now;

        // cy - py of a pixel row
        uint32_t numerator(uint32_t r) const {
            const float py = static_cast<float>(32 * tile_y + r) + 0.5f;
            return as_bits(as_float(cam[14]) - py);
        }

        bool colour(uint32_t pass_first, uint32_t pass_end) {
            for (uint32_t r = pass_first; r < pass_end; ++r) {
                light_row(r - row0, numbers, values);
                values[kLightProfRows]++;
            }
            return true;
        }

        // the rows' keys and points; the keys' time
        template <bool glass_form = false>
        void keys() {
            for (uint32_t r = first; r < end; ++r) {
                light_keys<glass_form>(r - row0, table, numerator(r), numbers.terms);
            }
            tensix_sync();
            now = km::wall();
            values[kLightProfKeys] += now - mark;
        }
    };

    // a row's texel addresses of taps [tap_first, tap_end) (row vectors; the zero
    // texel where a key is 0) from index slot 0
    struct ScanTaps {
        Pass& pass;
        uint32_t tap_first, tap_end;

        bool operator()(uint32_t row) {
            for (uint32_t tap = tap_first; tap < tap_end; ++tap) {
                if (row_addresses(
                        pass.pages,
                        from_window(tap_vector(row - pass.row0, tap), pass.vl),
                        kNoTags,
                        pass.index + 1024 * (tap - tap_first) + 32 * row,
                        pass.page_limit,
                        kZeroTexel,
                        false,
                        true,
                        pass.vl
                    ) < 0) {
                    return false;
                }
            }
            return true;
        }
    };

    // the taps' gather; `colour`: each row's colour after it
    struct GatherTaps {
        Pass& pass;
        uint32_t tap_first, tap_end;
        bool colour;

        bool operator()(uint32_t pass_first, uint32_t pass_end) {
            const uint32_t gathered = km::wall();
            for (uint32_t r = pass_first; r < pass_end; ++r) {
                for (uint32_t tap = tap_first; tap < tap_end; ++tap) {
                    to_window(
                        tap_vector(r - pass.row0, tap),
                        __riscv_vluxei32_v_u32m8(
                            pass.slots,
                            __riscv_vle32_v_u32m8(
                                pass.index + 1024 * (tap - tap_first) + 32 * r, pass.vl
                            ),
                            pass.vl
                        ),
                        pass.vl
                    );
                }
            }
            asm volatile("" ::: "memory");
            setup_k::setup_pass::order(
                word(tap_vector(pass_end - 1 - pass.row0, tap_end - 1)) + 62
            );
            pass.values[kLightProfGather] += km::wall() - gathered;
            return colour ? pass.colour(pass_first, pass_end) : true;
        }
    };

    // the field: a row's corner keys (the vector unit), their texel addresses
    // (direction 0's; the zero texel where a key is 0)
    struct FieldScan {
        Pass& pass;

        bool operator()(uint32_t row) {
            const uint32_t keyed_at = km::wall();
            field_keys(row - pass.row0, pass.table);
            tensix_sync();
            pass.values[kLightProfFieldKeys] += km::wall() - keyed_at;
            for (uint32_t corner = 0; corner < kFieldCorners; ++corner) {
                if (row_addresses(
                        pass.pages,
                        from_window(sx_vector(kSfKey + corner), pass.vl),
                        kNoTags,
                        pass.field_index + 1024 * corner + 32 * row,
                        pass.page_limit,
                        kZeroTexel,
                        false,
                        true,
                        pass.vl
                    ) < 0) {
                    return false;
                }
            }
            return true;
        }
    };

    // each row: weights, per axis the eight texels of the direction its normal faces
    // (128 d texels on) and their blend, I, the colour
    static_assert(kFieldDirectionBytes == 1u << 9);

    struct FieldRows {
        Pass& pass;

        __attribute__((noinline)) bool operator()(
            uint32_t pass_first, uint32_t pass_end
        ) {
            uint32_t* values = pass.values;
            const size_t vl = pass.vl;
            for (uint32_t r = pass_first; r < pass_end; ++r) {
                const uint32_t k = r - pass.row0;
                uint32_t at = km::wall();
                field_weights(k, pass.table);
                for (uint32_t axis = 0; axis < 3; ++axis) {
                    tensix_sync();  // the vector unit is done with the texels
                    uint32_t now = km::wall();
                    values[kLightProfFieldBlend] += now - at;
                    at = now;
                    const vuint32m8_t offset = (__riscv_vadd_vx_u32m8(
                        __riscv_vsll_vx_u32m8(
                            __riscv_vsrl_vx_u32m8(
                                from_window(plane_vector(kLvNormal + axis, k), vl),
                                31,
                                vl
                            ),
                            9,
                            vl
                        ),
                        2 * axis * kFieldDirectionBytes,
                        vl
                    ));
                    for (uint32_t corner = 0; corner < kFieldCorners; ++corner) {
                        to_window(
                            sx_vector(kSfTexel + corner),
                            __riscv_vluxei32_v_u32m8(
                                pass.slots,
                                __riscv_vadd_vv_u32m8(
                                    __riscv_vle32_v_u32m8(
                                        pass.field_index + 1024 * corner + 32 * r, vl
                                    ),
                                    offset,
                                    vl
                                ),
                                vl
                            ),
                            vl
                        );
                    }
                    asm volatile("" ::: "memory");
                    setup_k::setup_pass::order(
                        word(sx_vector(kSfTexel + kFieldCorners - 1)) + 62
                    );
                    now = km::wall();
                    values[kLightProfFieldGather] += now - at;
                    at = now;
                    field_blend(k, axis);
                }
                field_finish(pass.table);
                tensix_sync();
                values[kLightProfFieldBlend] += km::wall() - at;
                if (pass.glass) {
                    light_row<true>(k, pass.numbers, values);
                } else {
                    light_row(k, pass.numbers, values);
                }
                values[kLightProfRows]++;
            }
            return true;
        }
    };

    // Rows [first, end) in page passes of `scan` and `gather`, counted in `counts`.
    template <typename Scan, typename Gather>
    inline bool passes(Pass& pass, PassCounts& counts, Scan scan, Gather gather) {
        return page_passes(
            pass.waits,
            pass.ask,
            pass.done,
            pass.first,
            pass.end,
            pass.pages,
            counts,
            scan,
            gather
        );
    }

}  // namespace light_k
