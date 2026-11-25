"""The cost model: estimated cycles of tiles and bands, bands of even cost, items to cores."""

import itertools

import numpy as np

from prism.stages.raster.model.numbers import K, M
from prism_reference.raster.fill import TILES_X

# cycles per (triangle, tile), per row, per tile with triangles, per empty tile
COST = {
    "tri": M["RM_COST_TRI"],
    "row": M["RM_COST_ROW"],
    "tile": M["RM_COST_TILE"],
    "empty": M["RM_COST_EMPTY"],
}


def tile_cost(packed, offsets, members, cost=COST):
    """Estimated cycles of each tile: its triangles, their rows in it and the tile."""
    triangles = np.diff(offsets)
    tile = np.repeat(np.arange(len(triangles)), triangles)
    top = 32 * (tile // TILES_X)
    box_first_row = packed[members, K["kRecY0"]].astype(np.int64)
    box_last_row = packed[members, K["kRecY1"]].astype(np.int64)
    rows = np.minimum(box_last_row, top + 31) - np.maximum(box_first_row, top) + 1
    per_tile = np.bincount(tile, rows, minlength=len(triangles))
    busy = cost["tri"] * triangles + cost["row"] * per_tile + cost["tile"]
    return np.where(triangles > 0, busy, cost["empty"])


def cost_of(counts, rows, cost=COST):
    """Estimated cycles of each tile from COUNT's counters, as `tile_cost`."""
    tile_entries, tile_rows = counts.sum(axis=0), rows.sum(axis=0)
    busy = cost["tri"] * tile_entries + cost["row"] * tile_rows + cost["tile"]
    return np.where(tile_entries > 0, busy, cost["empty"])


def as_item(x):
    """(tile, first_row, end_row): a tile number alone is the whole tile."""
    if isinstance(x, tuple):
        return x
    return (int(x), 0, 32)


def band_ranks(packed, tile_ranks, tile, first_row, end_row):
    """The members of a tile whose rows reach into its rows [first_row, end_row)."""
    top = 32 * (tile // TILES_X)
    box_first_row = packed[tile_ranks, K["kRecY0"]].astype(np.int64)
    box_last_row = packed[tile_ranks, K["kRecY1"]].astype(np.int64)
    return tile_ranks[
        (box_first_row <= top + end_row - 1) & (box_last_row >= top + first_row)
    ]


def band_cost(packed, tile_ranks, tile, first_row, end_row, cost=COST):
    """Estimated cycles of a band of a tile, as `tile_cost` counts a tile."""
    top = 32 * (tile // TILES_X)
    band_members = band_ranks(packed, tile_ranks, tile, first_row, end_row)
    if len(band_members) == 0:
        return cost["empty"]
    box_first_row = packed[band_members, K["kRecY0"]].astype(np.int64)
    box_last_row = packed[band_members, K["kRecY1"]].astype(np.int64)
    rows = (
        np.minimum(box_last_row, top + end_row - 1)
        - np.maximum(box_first_row, top + first_row)
        + 1
    )
    return (
        cost["tri"] * len(band_members) + cost["row"] * int(rows.sum()) + cost["tile"]
    )


def split_tiles(packed, offsets, members, tiles, cost, target, max_bands=16):
    """(items, their costs): each tile of `tiles` whole, or, when its cost is above
    `target`, as bands of even rows of about equal estimated cost."""
    items, costs = [], []
    for tile in tiles:
        bands = min(max_bands, int(np.ceil(cost[tile] / target)))
        if bands < 2:
            items.append((tile, 0, 32))
            costs.append(cost[tile])
            continue
        tile_members = members[offsets[tile] : offsets[tile + 1]]
        top = 32 * (tile // TILES_X)
        box_first_row = np.clip(
            packed[tile_members, K["kRecY0"]].astype(np.int64) - top, 0, 31
        )
        box_last_row = np.clip(
            packed[tile_members, K["kRecY1"]].astype(np.int64) - top, 0, 31
        )
        # row weights: each row's coverage, a triangle's setup on its first row
        starts = np.bincount(box_first_row, minlength=33)
        cover = np.cumsum(starts - np.bincount(box_last_row + 1, minlength=33))[:32]
        row_weights = COST["row"] * cover + COST["tri"] * starts[:32]
        cumulative = np.cumsum(row_weights.reshape(16, 2).sum(axis=1))
        cuts = (
            np.searchsorted(cumulative, cumulative[-1] * np.arange(1, bands) / bands)
            + 1
        )
        bounds = np.unique(np.concatenate([[0], 2 * cuts, [32]]))
        for first_row, end_row in itertools.pairwise(bounds):
            items.append((tile, int(first_row), int(end_row)))
            costs.append(
                band_cost(packed, tile_members, tile, int(first_row), int(end_row))
            )
    return items, np.asarray(costs, dtype=np.float64)


def assign(cost, cores, mode="balanced"):
    """Tiles per core: round-robin over the tile numbers, or balanced by the tiles'
    costs (largest first to the least loaded core)."""
    cost = np.asarray(cost, dtype=np.float64).reshape(-1)
    if mode == "round-robin":
        return [list(range(core, len(cost), cores)) for core in range(cores)]
    if mode != "balanced":
        raise ValueError(f"unknown assignment {mode}")
    load = np.zeros(cores)
    per_core = [[] for _ in range(cores)]
    for tile in np.argsort(-cost, kind="stable"):
        core = int(np.argmin(load))
        per_core[core].append(int(tile))
        load[core] += cost[tile]
    return [sorted(tiles) for tiles in per_core]
