// Lit SHADE's transmit mode on the pack thread (a DEPTH view's glass layer, merging):
// each item's T (texture/kernels/transmit.hpp) over the opaque layer's 1/z, out as the
// opaque frame's planes with the band's kept codes at its rows' bytes of plane 1, the
// opaque surface's two parts as they came.
#pragma once

#include <stdint.h>

#include "../../transmit.hpp"
#include "../list.hpp"
#include "../profile.hpp"
#include "surface.hpp"

namespace shade_k {

    // Rows [first_row, end_row) of `planes` pages from `from` to `to`.
    inline void copy_rows(
        uint32_t to, uint32_t from, uint32_t planes, int32_t first_row, int32_t end_row
    ) {
        const uint32_t first = first_row * kRowBytes,
                       bytes = (end_row - first_row) * kRowBytes;
        for (uint32_t plane = 0; plane < planes; ++plane) {
            __builtin_memcpy(
                reinterpret_cast<void*>(to + plane * kOutPageBytes + first),
                reinterpret_cast<const void*>(from + plane * kOutPageBytes + first),
                bytes
            );
        }
    }

    // An item's records' T into part 0's pages 1 to 3, then the codes; false: the
    // list gave up.
    inline bool transmit_item(
        List& list,
        const Table& table,
        uint32_t records,
        uint32_t tile_y,
        int32_t first_row,
        int32_t end_row,
        uint32_t channels,
        const uint32_t* lanes,
        const float* depth,
        uint32_t out,
        size_t vl
    ) {
        float* t[transmit_k::kTransmitPlanes];
        for (uint32_t c = 0; c < transmit_k::kTransmitPlanes; ++c) {
            t[c] = reinterpret_cast<float*>(out + (1 + c) * kOutPageBytes);
        }
        transmit_k::t_ones(t, first_row, end_row, vl);
        const float loss = transmit_k::bits_float(transmit_k::kTransmitLossBits);
        for (uint32_t i = 0; i < records; ++i) {
            const volatile uint32_t* record = list.next();
            if (record == nullptr) {
                return false;
            }
            transmit_k::Pane pane;
            if (transmit_k::pane_of(
                    record,
                    table.material_words,
                    table.materials,
                    tile_y,
                    first_row,
                    end_row,
                    loss,
                    pane
                ) &&
                pane.first <= pane.last) {
                transmit_k::pane_rows(pane, lanes, tile_y, depth, t);
            }
        }
        asm volatile("fence" ::: "memory");
        transmit_k::t_codes(
            out + kOutPageBytes,
            first_row,
            end_row,
            channels,
            out + kOutPageBytes + first_row * kRowBytes
        );
        return true;
    }

    // Lit SHADE's transmit mode of one command: `opaque` the opaque layer's directory,
    // `grid` the frame's (grid.h), `channels` T's (1 or 3).
    [[gnu::noinline]] inline void shade_transmit(
        const compute_mail::Waits& waits, uint32_t grid, uint32_t channels
    ) {
        Counters counters;
        uint32_t* values = counters.values;
        const uint32_t started = km::wall();
        bool succeeded = true;
        const uint32_t table_address = compute_mail::front(waits, kFieldFrameTable, 1);
        Table table;
        if (!table.at(table_address)) {
            compute_mail::stop(waits.stops, kGaveBadItem, kWhereShadeBad);
            succeeded = false;
        }
        uint32_t* lanes = reinterpret_cast<uint32_t*>(
            texel_space::texel_work(compute_mail::write_ptr(kFieldCommandSpace))
        );
        uint32_t lanes_x = 0xFFFFFFFF;  // the tile column the lanes are for
        List list{waits};
        const size_t vl = __riscv_vsetvl_e32m8(32);
        while (succeeded) {
            const volatile uint32_t* header = list.next();
            if (header == nullptr) {
                succeeded = false;
                break;
            }
            if (header[0] == kMarkEnd) {
                break;
            }
            const uint32_t tile = header[kHdrTile], records = header[kHdrCount];
            const int32_t first_row = header[kHdrRow0], end_row = header[kHdrRow1];
            if (!(0 <= first_row && first_row < end_row && end_row <= 32 &&
                  tile < kTileCapacity)) {
                compute_mail::stop(waits.stops, kGaveBadItem, kWhereShadeBad);
                succeeded = false;
                break;
            }
            uint32_t mark = km::wall();
            const uint32_t planes = compute_mail::front(
                waits, kFieldInPlanes, 2 * kPlanes
            );
            if (planes == 0 ||
                !compute_mail::reserve(
                    waits, kFieldOutRing, kLitParts * kShadeOutPages
                )) {
                succeeded = false;
                break;
            }
            values[kShadeProfWaitIn] += km::wall() - mark;
            mark = km::wall();
            const uint32_t across = grid_of(grid).across;
            if (tile % across != lanes_x) {
                lanes_x = tile % across;
                transmit_k::lane_words(lanes, lanes_x);
            }
            Parts parts;
            parts.place(compute_mail::write_ptr(kFieldOutRing));
            const uint32_t opaque_planes = opaque_after(planes);
            copy_rows(parts.page(0, 0), opaque_planes, kPlanes, first_row, end_row);
            if (!transmit_item(
                    list,
                    table,
                    records,
                    tile / across,
                    first_row,
                    end_row,
                    channels,
                    lanes,
                    reinterpret_cast<const float*>(opaque_planes),
                    parts.page(0, 0),
                    vl
                ) ||
                !compute_mail::pop(waits, kFieldInPlanes, 2 * kPlanes)) {
                succeeded = false;
                break;
            }
            values[kShadeProfRecord] += km::wall() - mark;
            mark = km::wall();
            // the opaque surface's two parts, as they came
            for (uint32_t part = 1; part < kLitParts && succeeded; ++part) {
                const uint32_t surface = compute_mail::front(
                    waits, kFieldInPlanes, kPlanes
                );
                if (surface == 0) {
                    succeeded = false;
                    break;
                }
                copy_rows(parts.page(part, 0), surface, kPlanes, first_row, end_row);
                succeeded = compute_mail::pop(waits, kFieldInPlanes, kPlanes);
            }
            if (!succeeded) {
                break;
            }
            asm volatile("fence" ::: "memory");
            const uint32_t last_word = kRowBytes / 4 * end_row - 1;
            for (uint32_t part = 0; part < kLitParts; ++part) {
                compute_mail::push(
                    kFieldOutRing,
                    parts.page(part, kPlanes - 1) + 4 * last_word,
                    kShadeOutPages
                );
            }
            values[kShadeProfOut] += km::wall() - mark;
            values[kShadeProfTiles]++;
        }
        texel_pages::ask_end(waits, kFieldTexelAsks);
        list.end();
        if (table_address != 0) {
            compute_mail::pop(waits, kFieldFrameTable, 1);
        }
        compute_mail::end_mails();
        if (succeeded) {
            profile_out(waits, counters, started);
        }
    }

}  // namespace shade_k
