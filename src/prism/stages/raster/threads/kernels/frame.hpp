// The frame's page as the geometry thread and the sums read it: a layer's words, a
// range of the count and place pulls checked against its layer, the slices of the
// view's grid. Plain arithmetic over the page's words (frame.h), on any CPU.
#pragma once

#include <stdint.h>

#include "geometry.h"

namespace geometry_k {

    // Word `word` (TF_L_*) of layer `layer` of the frame's page.
    template <typename Words>
    inline uint32_t layer_word(const Words& page, uint32_t layer, uint32_t word) {
        return page[TF_LAYER_AT + TF_LAYER_WORDS * layer + word];
    }

    // The layers of the page, at most a record's.
    template <typename Words>
    inline uint32_t layers_of(const Words& page) {
        const uint32_t layers = page[TF_LAYER_COUNT];
        return layers < TR_LAYERS ? layers : TR_LAYERS;
    }

    // Whether a range of the count and place pulls (prism_frame::Range) lies in a
    // layer of the page: blocks [first_block, first_block + blocks) of the layer's.
    template <typename Words, typename Range>
    inline bool range_fits(const Words& page, const Range& range) {
        if (range.layer >= layers_of(page) || range.blocks == 0) {
            return false;
        }
        const uint32_t blocks = layer_word(page, range.layer, TF_L_BLOCKS);
        return range.first_block < blocks && range.blocks <= blocks - range.first_block;
    }

    // The view's slices: runs of TF_SLICE_TILES tiles along a row of the grid, a row
    // cut into ceil(TX / slice tiles) of them; slice s is (s % across, s / across) in
    // the slice grid.
    struct Slices {
        uint32_t across;   // the grid's tiles a row (TX)
        uint32_t tiles;    // a slice's tiles (TF_SLICE_TILES)
        uint32_t per_row;  // slices a row of tiles
        uint32_t count;    // slices of the view (TF_SLICE_COUNT)
    };

    // The page's slices; count 0 when the page's numbers do not make a slice grid
    // within the capacity.
    template <typename Words>
    inline Slices slices_of(const Words& page) {
        const Grid grid = grid_of(page[TF_GRID]);
        const uint32_t tiles = page[TF_SLICE_TILES];
        if (tiles == 0 || tiles > kSliceTilesMost) {
            return {grid.across, 1, 1, 0};
        }
        const uint32_t per_row = (grid.across + tiles - 1) / tiles;
        const uint32_t count = page[TF_SLICE_COUNT];
        const bool fits = count == per_row * grid.down && count <= kSlices &&
            grid.across * grid.down <= kTileCapacity;
        return {grid.across, tiles, per_row, fits ? count : 0};
    }

    // A slice's tiles: the first (ty TX + tx) and how many along its row.
    struct SliceTiles {
        uint32_t first;
        uint32_t count;
    };

    inline SliceTiles tiles_of_slice(const Slices& slices, uint32_t slice) {
        const uint32_t row = slice / slices.per_row;
        const uint32_t column = (slice % slices.per_row) * slices.tiles;
        const uint32_t left = slices.across - column;
        return {
            row * slices.across + column, left < slices.tiles ? left : slices.tiles
        };
    }

    // The slice that holds tile `tile`.
    inline uint32_t slice_of(const Slices& slices, uint32_t tile) {
        const uint32_t row = tile / slices.across, column = tile % slices.across;
        return row * slices.per_row + column / slices.tiles;
    }

    // The word of tile `tile` in a positions page (geometry.h).
    inline uint32_t tile_word(const Slices& slices, uint32_t tile) {
        const uint32_t row = tile / slices.across, column = tile % slices.across;
        const uint32_t slice = row * slices.per_row + column / slices.tiles;
        return slice * kSliceTilesMost + column % slices.tiles;
    }

}  // namespace geometry_k
