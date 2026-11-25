"""What COUNT gives: each core's partition of the blocks, its entries, counters and
histograms."""

import numpy as np

from prism.stages.raster.model.numbers import GROUPS, LANES, TILES
from prism_reference.raster.fill import TILES_X
from prism_reference.scene.frame import TILE


def partitions(blocks, cores):
    """First block of every core and the end: (cores + 1,), contiguous, ascending."""
    return (np.arange(cores + 1) * blocks) // cores


def entries(records, triangles, cores):
    """Every (record, tile) entry in record order: its tile, the core whose partition
    holds the record, and its first and last row inside the tile."""
    edge = partitions(-(-triangles // LANES), cores) * LANES
    box = records["box"].astype(np.int64)
    first_tile_x, last_tile_x = box[:, 0] // TILE, box[:, 1] // TILE
    first_tile_y, last_tile_y = box[:, 2] // TILE, box[:, 3] // TILE
    tiles_across, tiles_down = (
        last_tile_x - first_tile_x + 1,
        last_tile_y - first_tile_y + 1,
    )
    per_record = tiles_across * tiles_down
    record = np.repeat(np.arange(len(box)), per_record)
    local = np.arange(per_record.sum()) - np.repeat(
        np.cumsum(per_record) - per_record, per_record
    )
    tile_y = first_tile_y[record] + local // tiles_across[record]
    tile = tile_y * TILES_X + first_tile_x[record] + local % tiles_across[record]
    top_row = TILE * tile_y
    first_row = np.maximum(box[record, 2], top_row) - top_row
    last_row = np.minimum(box[record, 3], top_row + 31) - top_row
    core = np.searchsorted(edge, records["tri"][record], side="right") - 1
    return {
        "record": record,
        "tile": tile,
        "core": core,
        "first_row": first_row,
        "last_row": last_row,
    }


def counters(records, triangles, cores):
    """What COUNT writes per core: entries and rows of each tile (cores, tiles), each
    core counting its partition of the triangles."""
    table = entries(records, triangles, cores)
    cell = table["core"] * TILES + table["tile"]
    size = cores * TILES
    entry_counts = np.bincount(cell, minlength=size).reshape(cores, TILES)
    rows = np.bincount(cell, table["last_row"] - table["first_row"] + 1, minlength=size)
    return entry_counts.astype(np.int64), rows.astype(np.int64).reshape(cores, TILES)


def histograms(records, triangles, cores):
    """What COUNT keeps per core: for every tile, how many of its entries start, and
    how many end, in each 2-row group (cores, tiles, GROUPS) twice."""
    table = entries(records, triangles, cores)
    base = (table["core"] * TILES + table["tile"]) * GROUPS
    size = cores * TILES * GROUPS
    shape = (cores, TILES, GROUPS)
    starts = np.bincount(base + table["first_row"] // 2, minlength=size).reshape(shape)
    ends = np.bincount(base + table["last_row"] // 2, minlength=size).reshape(shape)
    return starts.astype(np.int64), ends.astype(np.int64)
