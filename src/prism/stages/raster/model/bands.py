"""Heavy tiles cut into bands of even rows: which tiles, where the cuts fall, the items."""

import itertools

import numpy as np

from prism.stages.raster.model.cost import COST, cost_of
from prism.stages.raster.model.numbers import GROUPS, MAX_BANDS, SPLIT


def heavy_tiles(counts, rows, cores, split=SPLIT):
    """(tile, bands) of every tile to cut: above `split` of a core's mean load, in
    up to MAX_BANDS bands; none when no tile is above the mean."""
    cost = cost_of(counts, rows)
    mean = cost.sum() / cores
    if cost.max() <= mean:
        return []
    bands = np.minimum(MAX_BANDS, np.ceil(cost / (split * mean))).astype(int)
    return [(int(tile), int(bands[tile])) for tile in np.flatnonzero(bands >= 2)]


def cover_of(starts, ends):
    """Entries reaching each 2-row group, from the start and end counts (GROUPS,)."""
    return np.cumsum(starts) - np.concatenate([[0], np.cumsum(ends)[:-1]])


def cuts(starts, ends, bands):
    """Band bounds in rows (even, 0 to 32) for `bands` bands of about equal estimated
    cost, from the tile's start and end counts summed over the cores."""
    weights = 2 * COST["row"] * cover_of(starts, ends) + COST["tri"] * starts
    cumulative = np.cumsum(weights).astype(np.int64)
    # the first group whose sum reaches j / bands of the whole, in integers
    groups = (
        np.searchsorted(bands * cumulative, cumulative[-1] * np.arange(1, bands)) + 1
    )
    return np.unique(np.concatenate([[0], 2 * groups, [GROUPS * 2]])).astype(int)


def band_count(starts, ends, first_row, end_row):
    """Entries reaching rows [first_row, end_row): starting before end_row less ending
    before first_row (starts, ends: (..., GROUPS))."""
    return starts[..., : end_row // 2].sum(-1) - ends[..., : first_row // 2].sum(-1)


def items_of(counts, rows, heavy, starts, ends):
    """Items in tile order (tile, first_row, end_row), with per item the entries of
    every setup core (cores, items) and the estimated cost. starts, ends: (cores,
    len(heavy), GROUPS), the heavy tiles' counts."""
    per_core, cost, items = [], [], []
    tile_cost = cost_of(counts, rows)
    heavy_index = {tile: position for position, (tile, _) in enumerate(heavy)}
    for tile in range(counts.shape[1]):
        if tile not in heavy_index:
            items.append((tile, 0, 32))
            per_core.append(counts[:, tile])
            cost.append(tile_cost[tile])
            continue
        position = heavy_index[tile]
        tile_starts, tile_ends = starts[:, position], ends[:, position]
        bounds = cuts(tile_starts.sum(0), tile_ends.sum(0), heavy[position][1])
        cover = cover_of(tile_starts.sum(0), tile_ends.sum(0))
        for first_row, end_row in itertools.pairwise(bounds):
            band_entries = band_count(tile_starts, tile_ends, first_row, end_row)
            items.append((tile, int(first_row), int(end_row)))
            per_core.append(band_entries)
            estimated_rows = int(2 * cover[first_row // 2 : end_row // 2].sum())
            busy = COST["tri"] * band_entries.sum() + COST["row"] * estimated_rows
            busy += COST["tile"]
            cost.append(busy if band_entries.sum() > 0 else COST["empty"])
    return items, np.stack(per_core, axis=1), np.asarray(cost, dtype=np.int64)
