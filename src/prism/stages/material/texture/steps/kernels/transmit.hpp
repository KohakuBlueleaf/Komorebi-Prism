// The glass layer of a DEPTH view on the pack CPU (the material step), its planes in
// L1: T (texture/kernels/transmit.hpp) into the glass layer's red, green and blue pages
// of the band (1 where none).
#pragma once

#include <stdint.h>

#include <riscv_vector.h>

#include "../../../../raster/steps/kernels/lists.hpp"
#include "../../kernels/transmit.hpp"
#include "run.hpp"

namespace material_step {

    using namespace transmit_k;

    // The glass layer of a DEPTH view's band (`list` its records, the tile's column
    // `tile_x`): T into its planes at `glass` (pages 1 to 3), against the opaque
    // layer's 1/z (the first page at `opaque`). False: gave up (recorded).
    template <typename List>
    __attribute__((noinline)) bool transmit_layer(
        List& list, const Run& run, uint32_t tile_x, uint32_t glass, uint32_t opaque
    ) {
        const size_t vl = run.vl;
        float* t[kTransmitPlanes];
        for (uint32_t c = 0; c < kTransmitPlanes; ++c) {
            t[c] = reinterpret_cast<float*>(glass + (1 + c) * fill_k::kOutPageBytes);
        }
        t_ones(t, run.first_row, run.end_row, vl);
        uint32_t* lanes = run.index;  // the texel addresses' words: no texels here
        lane_words(lanes, tile_x);
        const float loss = bits_float(kTransmitLossBits);
        const float* depth = reinterpret_cast<const float*>(opaque);
        while (const volatile uint32_t* record = list.next()) {
            Pane pane;
            if (pane_of(
                    record,
                    run.table.material_words,
                    run.table.materials,
                    run.tile_y,
                    run.first_row,
                    run.end_row,
                    loss,
                    pane
                ) &&
                pane.first <= pane.last) {
                pane_rows(pane, lanes, run.tile_y, depth, t);
            }
        }
        asm volatile("fence" ::: "memory");
        return list.end_walk();
    }

}  // namespace material_step
