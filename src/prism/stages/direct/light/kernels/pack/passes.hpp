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

#if defined(PRISM_LIGHT_TRANSMIT)
        // T's numbers from the table: on when the sun's map has T and the rows' shadow
        // taps are keyed; its channels' place, mask and spread (grey: one byte, three
        // equal channels)
        void transmit_tile() {
            const bool grey = table[kLtTransmitChannels] == 1;
            float first;  // the map's 1 + first page, float bits in the table
            __builtin_memcpy(&first, table + kLtShadowFirst, 4);
            TransmitTile& t = tile();
            t.on = (numbers.terms & kTermShadow) != 0 && table[kLtTransmitFirst] != 0;
            numbers.transmit = t.on;
            t.first = table[kLtTransmitFirst];
            t.map_first = static_cast<uint32_t>(first);
            t.page_shift = grey ? 4u : 2u;
            t.byte_mask = grey ? 3u : 0u;
            t.word_shift = grey ? 2u : 0u;
            t.mask = grey ? 0xFFu : 0xFFFFFFu;
            t.spread = grey ? 0x010101u : 1u;
        }

        // T's taps' texel addresses, then their codes: the light work's words after
        // the field's corners (kLwTransmit)
        uint32_t* transmit_words() const {
            return field_index + 1024 * kFieldCorners;
        }

        // T's numbers of the tile (transmit_tile), after its taps' words
        TransmitTile& tile() const {
            return *reinterpret_cast<TransmitTile*>(transmit_words() + kTransmitWords);
        }

        // row r's T at its taps (their codes in `transmit`) into the row scratch, each
        // channel a byte of the code
        [[gnu::noinline]] void transmit_in(uint32_t r) {
            if (!tile().on) {
                return;
            }
            tensix_sync();
            for (uint32_t tap = 0; tap < kLightKeys; ++tap) {
                const vuint32m8_t code = __riscv_vle32_v_u32m8(
                    transmit_words() + 1024 * tap + 32 * r, vl
                );
                for (uint32_t c = 0; c < 3; ++c) {
                    const vuint32m8_t byte = __riscv_vand_vx_u32m8(
                        __riscv_vsrl_vx_u32m8(code, 8 * c, vl), 0xFF, vl
                    );
                    to_window(
                        sx_vector(kSxTransmit + kLightKeys * c + tap),
                        __riscv_vreinterpret_v_f32m8_u32m8(__riscv_vfmul_vf_f32m8(
                            __riscv_vfcvt_f_xu_v_f32m8(byte, vl),
                            held_float(0x3B808081),
                            vl
                        )),
                        vl
                    );
                }
            }
            asm volatile("" ::: "memory");
            setup_k::setup_pass::order(
                word(sx_vector(kSxTransmit + 3 * kLightKeys - 1)) + 62
            );
        }
#endif

        bool colour(uint32_t pass_first, uint32_t pass_end) {
            for (uint32_t r = pass_first; r < pass_end; ++r) {
#if defined(PRISM_LIGHT_TRANSMIT)
                transmit_in(r);
#endif
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

#if defined(PRISM_LIGHT_TRANSMIT)
    // Shadow taps' T keys from their map keys (0: off the map), in place, 16 lanes at
    // a time: a tile's block's word (transmit.h; the map's tile the key's page, its
    // texel's row and column the key's).
    inline void transmit_keys(uint32_t* keys, const TransmitTile& t) {
        const size_t vl = __riscv_vsetvl_e32m4(16);
        for (uint32_t half = 0; half < 2; ++half) {
            uint32_t* at = keys + 16 * half;
            const vuint32m4_t key = __riscv_vle32_v_u32m4(at, vl);
            const vbool8_t on = __riscv_vmsgeu_vx_u32m4_b8(key, 1u << 10, vl);
            const vuint32m4_t texel = __riscv_vand_vx_u32m4(key, 1023, vl);
            const vuint32m4_t tile = __riscv_vsub_vx_u32m4(
                __riscv_vsrl_vx_u32m4(key, 10, vl), t.map_first, vl
            );
            // the block's 256 texels in its page, then (row / 2) 16 + column / 2: a
            // byte's place (grey) or a word's
            const vuint32m4_t place = __riscv_vadd_vv_u32m4(
                __riscv_vadd_vv_u32m4(
                    __riscv_vsll_vx_u32m4(
                        __riscv_vand_vx_u32m4(tile, (1u << t.page_shift) - 1, vl), 8, vl
                    ),
                    __riscv_vsll_vx_u32m4(__riscv_vsrl_vx_u32m4(texel, 6, vl), 4, vl),
                    vl
                ),
                __riscv_vsrl_vx_u32m4(__riscv_vand_vx_u32m4(texel, 31, vl), 1, vl),
                vl
            );
            const vuint32m4_t page = __riscv_vadd_vx_u32m4(
                __riscv_vsrl_vx_u32m4(tile, t.page_shift, vl), t.first, vl
            );
            __riscv_vse32_v_u32m4(
                at,
                __riscv_vmerge_vvm_u32m4(
                    __riscv_vmv_v_x_u32m4(0, vl),
                    __riscv_vor_vv_u32m4(
                        __riscv_vsll_vx_u32m4(page, 10, vl),
                        __riscv_vsrl_vx_u32m4(place, t.word_shift, vl),
                        vl
                    ),
                    on,
                    vl
                ),
                vl
            );
        }
        asm volatile("" ::: "memory");
    }

    // a row's T texel addresses (the one texel where a key is 0) into `to`, each its
    // byte's (grey: the column / 2's low bits); false when the pages do not fit
    [[gnu::noinline]] inline bool transmit_addresses(
        Pass& pass, uint32_t row, uint32_t* to
    ) {
        const size_t vl = pass.vl;
        for (uint32_t tap = 0; tap < kLightKeys; ++tap) {
            const uint32_t window = tap_vector(row - pass.row0, tap);
            uint32_t* at = to + 1024 * tap + 32 * row;
            __riscv_vse32_v_u32m8(at, from_window(window, vl), vl);
            transmit_keys(at, pass.tile());
            if (row_addresses(
                    pass.pages,
                    __riscv_vle32_v_u32m8(at, vl),
                    kNoTags,
                    at,
                    pass.page_limit,
                    kOneTexel,
                    false,
                    true,
                    vl
                ) < 0) {
                return false;
            }
            const vuint32m8_t byte = __riscv_vand_vx_u32m8(
                __riscv_vsrl_vx_u32m8(
                    __riscv_vand_vx_u32m8(from_window(window, vl), 31, vl), 1, vl
                ),
                pass.tile().byte_mask,
                vl
            );
            __riscv_vse32_v_u32m8(
                at, __riscv_vadd_vv_u32m8(__riscv_vle32_v_u32m8(at, vl), byte, vl), vl
            );
        }
        return true;
    }
#endif

    // a row's texel addresses of taps [tap_first, tap_end) (row vectors; the zero
    // texel where a key is 0) from index slot 0, and with the shadow's taps their
    // T's (transmit_addresses)
    struct ScanTaps {
        Pass& pass;
        uint32_t tap_first, tap_end;

        bool operator()(uint32_t row) {
#if defined(PRISM_LIGHT_TRANSMIT)
            if (tap_first == 0 && pass.tile().on &&
                !transmit_addresses(pass, row, pass.transmit_words())) {
                return false;
            }
#endif
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

#if defined(PRISM_LIGHT_TRANSMIT)
    // rows [first, end)'s T codes at their taps from the slots, over their addresses:
    // the word at the address's, shifted by its byte, masked and spread
    [[gnu::noinline]] inline void gather_transmit(
        Pass& pass, uint32_t first, uint32_t end
    ) {
        const size_t vl = pass.vl;
        for (uint32_t r = first; r < end; ++r) {
            for (uint32_t tap = 0; tap < kLightKeys; ++tap) {
                uint32_t* at = pass.transmit_words() + 1024 * tap + 32 * r;
                const vuint32m8_t address = __riscv_vle32_v_u32m8(at, vl);
                const vuint32m8_t word = __riscv_vluxei32_v_u32m8(
                    pass.slots, __riscv_vand_vx_u32m8(address, ~3u, vl), vl
                );
                const vuint32m8_t code = __riscv_vand_vx_u32m8(
                    __riscv_vsrl_vv_u32m8(
                        word,
                        __riscv_vsll_vx_u32m8(
                            __riscv_vand_vx_u32m8(address, 3, vl), 3, vl
                        ),
                        vl
                    ),
                    pass.tile().mask,
                    vl
                );
                __riscv_vse32_v_u32m8(
                    at, __riscv_vmul_vx_u32m8(code, pass.tile().spread, vl), vl
                );
            }
        }
        asm volatile("" ::: "memory");
    }
#endif

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
#if defined(PRISM_LIGHT_TRANSMIT)
            if (tap_first == 0 && pass.tile().on) {
                gather_transmit(pass, pass_first, pass_end);
            }
#endif
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
#if defined(PRISM_LIGHT_TRANSMIT)
                pass.transmit_in(r);
#endif
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
