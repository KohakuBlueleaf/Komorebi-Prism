// A slice's arithmetic, from the counts summed over the cores: which tiles are cut and
// into how many bands, where a cut tile's rows are cut, a band's entries, the slice's
// items in order of weight with each layer's list slot. Plain C++ on any CPU.
#pragma once

#include <stdint.h>

#include "../geometry.h"

namespace geometry_k {

    // An item of a slice: a whole tile or a band of a cut tile.
    struct Item {
        uint32_t tile;
        uint32_t rows;    // first_row | end_row << kBandRowsEndShift
        uint32_t weight;  // its entries over every layer
        uint32_t column;  // its tile's place in the slice's run
        uint32_t entry;   // a band: its band entry (positions page); a whole tile: 0
        uint32_t entries[TR_LAYERS];
        uint32_t slot[TR_LAYERS];  // its list's first slot, from the slice's place
    };

    constexpr uint32_t kWholeRows = kTileRows << kBandRowsEndShift;

    inline uint32_t first_row(uint32_t rows) {
        return rows & 0xFF;
    }

    inline uint32_t end_row(uint32_t rows) {
        return rows >> kBandRowsEndShift;
    }

    // The bands of a tile of weight `weight` above `heavy` (0: never cut): its weight
    // over `heavy`, rounded up, at most kBandsMost and `room`; 1: the tile is whole.
    inline uint32_t bands_of(uint32_t weight, uint32_t heavy, uint32_t room) {
        if (heavy == 0 || weight <= heavy) {
            return 1;
        }
        uint32_t bands = (weight + heavy - 1) / heavy;
        bands = bands < kBandsMost ? bands : kBandsMost;
        bands = bands < room ? bands : room;
        return bands < 2 ? 1 : bands;
    }

    // The bands each of `tiles` tiles is cut into (`weights` theirs), so that the
    // slice's items stay within kSliceRecords: a tile takes at most the room its
    // followers leave, in the run's order.
    inline void plan_bands(
        const uint32_t* weights, uint32_t tiles, uint32_t heavy, uint32_t* bands
    ) {
        uint32_t items = 0;
        for (uint32_t column = 0; column < tiles; ++column) {
            const uint32_t room = kSliceRecords - items - (tiles - 1 - column);
            bands[column] = bands_of(weights[column], heavy, room);
            items += bands[column];
        }
    }

    // The rows where a tile is cut into `bands` bands of about equal cover (the entries
    // reaching each 2-row group, from `starts` and `ends` summed over the cores and the
    // layers): bounds[0] = 0 < bounds[1] < ... < bounds[n] = 32, even; n returned.
    inline uint32_t cut_rows(
        const uint32_t* starts, const uint32_t* ends, uint32_t bands, uint32_t* bounds
    ) {
        uint64_t cumulative[kGroups];
        uint64_t started = 0, ended = 0, sum = 0;
        for (uint32_t group = 0; group < kGroups; ++group) {
            started += starts[group];
            sum += started - ended;  // the cover of this group
            ended += ends[group];
            cumulative[group] = sum;
        }
        uint32_t count = 0, group = 0;
        bounds[count++] = 0;
        for (uint32_t part = 1; part < bands; ++part) {
            const uint64_t target = cumulative[kGroups - 1] * part;
            while (group < kGroups && bands * cumulative[group] < target) {
                ++group;
            }
            const uint32_t row = 2 * (group + 1);
            if (row < kTileRows && row > bounds[count - 1]) {
                bounds[count++] = row;
            }
        }
        bounds[count] = kTileRows;
        return count;
    }

    // Entries reaching rows [first_row, end_row): those starting before end_row less
    // those ending before first_row (`starts`, `ends`: kGroups counts).
    template <typename Counts>
    inline uint32_t band_entries(
        const Counts& starts, const Counts& ends, uint32_t first_row, uint32_t end_row
    ) {
        uint32_t before_end = 0, before_first = 0;
        for (uint32_t group = 0; group < end_row / 2; ++group) {
            before_end += starts[group];
        }
        for (uint32_t group = 0; group < first_row / 2; ++group) {
            before_first += ends[group];
        }
        return before_end - before_first;
    }

    // Whether item a comes before item b: the heavier first; then the lower tile, then
    // the lower first row.
    inline bool before(const Item& a, const Item& b) {
        if (a.weight != b.weight) {
            return a.weight > b.weight;
        }
        if (a.tile != b.tile) {
            return a.tile < b.tile;
        }
        return first_row(a.rows) < first_row(b.rows);
    }

    // The order of `count` items (`order`: their indices) and each layer's list slots
    // in that order, from the slice's place; `totals` each layer's entries.
    inline void order_items(
        Item* items, uint32_t count, uint32_t layers, uint32_t* order, uint32_t* totals
    ) {
        for (uint32_t i = 0; i < count; ++i) {
            uint32_t at = i;
            while (at > 0 && before(items[i], items[order[at - 1]])) {
                order[at] = order[at - 1];
                --at;
            }
            order[at] = i;
        }
        for (uint32_t layer = 0; layer < TR_LAYERS; ++layer) {
            uint32_t slot = 0;
            for (uint32_t k = 0; k < count; ++k) {
                Item& item = items[order[k]];
                item.slot[layer] = slot;
                slot += layer < layers ? item.entries[layer] : 0;
            }
            totals[layer] = slot;
        }
    }

    // Item `item`'s record (record.h) into `words` (TR_WORDS): its tile and rows, its
    // weight, its layers, its page (its tile), each layer's slot and entries.
    inline void record_of(const Item& item, uint32_t layers, uint32_t* words) {
        for (uint32_t word = 0; word < TR_WORDS; ++word) {
            words[word] = 0;
        }
        words[0] = item.tile | first_row(item.rows) << 16 | end_row(item.rows) << 24;
        words[1] = item.weight;
        for (uint32_t layer = 0; layer < layers; ++layer) {
            words[2] |= (item.entries[layer] != 0 ? 1u : 0u) << layer;
            words[TR_LAYER_SLOT(layer)] = item.slot[layer];
            words[TR_LAYER_ENTRIES(layer)] = item.entries[layer];
        }
        words[3] = item.tile;
    }

}  // namespace geometry_k
