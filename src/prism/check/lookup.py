"""The page passes of a frame's lookups as the card makes them: each layer's items and
their deal to the cores (the raster model), each row's distinct pages, the passes of
rows whose pages fit the slots, and the pages a core's slots would keep."""

import itertools
from collections import OrderedDict

import numpy as np

from prism.core.headers import INCLUDE, constexpr
from prism.stages.direct.light.model.numbers import KERNELS as LIGHT_KERNELS
from prism.stages.raster.model.bands import band_count, cuts, heavy_tiles
from prism.stages.raster.model.cost import COST, assign, cost_of
from prism.stages.raster.model.numbers import GROUPS
from prism_reference.raster.frames import layer_scene
from prism_reference.raster.setup import grid, setup
from prism_reference.scene.frame import TILE

SLOTS = constexpr(INCLUDE / "texel_pages" / "protocol.h")["kShadeSlots"]
# LIGHT's rows a pass
QUARTER = constexpr(LIGHT_KERNELS / "pack" / "dst.hpp")["kLightRows"]
RECTANGLES = (2, 4, 8, 16, 32)


def layer_counts(scene, keep):
    """COUNT's numbers of a layer (`keep` its triangles), summed over the cores: per tile
    its entries and rows (tiles,), its entries' first and last 2-row groups (tiles,
    GROUPS)."""
    across, down = grid(scene)
    tiles = across * down
    box = setup(layer_scene(scene, keep))["box"].astype(np.int64)
    tx0, tx1, ty0, ty1 = (
        box[:, 0] // TILE,
        box[:, 1] // TILE,
        box[:, 2] // TILE,
        box[:, 3] // TILE,
    )
    per = (tx1 - tx0 + 1) * (ty1 - ty0 + 1)
    record = np.repeat(np.arange(len(box)), per)
    local = np.arange(per.sum()) - np.repeat(np.cumsum(per) - per, per)
    width = (tx1 - tx0 + 1)[record]
    tile_y = ty0[record] + local // width
    tile = tile_y * across + tx0[record] + local % width
    top = TILE * tile_y
    first = np.maximum(box[record, 2], top) - top
    last = np.minimum(box[record, 3], top + TILE - 1) - top
    entries = np.bincount(tile, minlength=tiles)
    rows = np.bincount(tile, last - first + 1, minlength=tiles).astype(np.int64)
    starts = np.zeros((tiles, GROUPS), dtype=np.int64)
    ends = np.zeros((tiles, GROUPS), dtype=np.int64)
    np.add.at(starts, (tile, first // 2), 1)
    np.add.at(ends, (tile, last // 2), 1)
    return entries, rows, starts, ends


def layer_deal(scene, keep, cores):
    """A layer's items (tile, first_row, end_row, entries) in tile order, heavy tiles cut
    into bands, and per core its items' indices in order (the balanced deal)."""
    entries, rows, starts, ends = layer_counts(scene, keep)
    heavy = dict(heavy_tiles(entries[None], rows[None], cores))
    tile_cost = cost_of(entries[None], rows[None])
    items, cost = [], []
    for tile in range(len(entries)):
        if tile not in heavy:
            items.append((tile, 0, TILE, int(entries[tile])))
            cost.append(tile_cost[tile])
            continue
        bounds = cuts(starts[tile], ends[tile], heavy[tile])
        cover = np.cumsum(starts[tile]) - np.concatenate(
            [[0], np.cumsum(ends[tile])[:-1]]
        )
        for first_row, end_row in itertools.pairwise(bounds):
            count = int(band_count(starts[tile], ends[tile], first_row, end_row))
            items.append((tile, int(first_row), int(end_row), count))
            estimated = int(2 * cover[first_row // 2 : end_row // 2].sum())
            busy = COST["tri"] * count + COST["row"] * estimated + COST["tile"]
            cost.append(busy if count > 0 else COST["empty"])
    return items, assign(np.asarray(cost), cores)


def row_sets(pages, across):
    """Each tile row's distinct pages: a list indexed by row y x across + tile column,
    of sorted arrays, from pages (H, W, K) (negative: none)."""
    height = pages.shape[0]
    ys, xs, _ = np.nonzero(pages >= 0)
    page = pages[pages >= 0]
    row = ys * across + xs // TILE
    key = np.unique(row.astype(np.int64) << 32 | page)
    row_of, page_of = key >> 32, key & 0xFFFFFFFF
    bounds = np.searchsorted(row_of, np.arange(height * across + 1))
    return [page_of[a:b] for a, b in itertools.pairwise(bounds)]


def item_passes(sets, across, item, unit, slots):
    """The passes (sets of pages) of an item (tile, first_row, end_row, _): its rows in
    units of `unit` rows (32: the item), each unit in passes of rows whose pages fit."""
    tile, first_row, end_row, _ = item
    tx, ty = tile % across, tile // across
    passes = []
    for start in range(0, TILE, unit):
        lo, hi = max(first_row, start), min(end_row, start + unit)
        if lo >= hi:
            continue
        current = set()
        for r in range(lo, hi):
            row = sets[(TILE * ty + r) * across + tx]
            joined = current.union(row.tolist())
            if len(joined) > slots:
                passes.append(current)
                current = set(row.tolist())
            else:
                current = joined
        passes.append(current)
    return passes


def frame_passes(sets, across, items, deal, unit, slots=SLOTS, skip_empty=False):
    """Per core its items' passes in order: a list a core of (item index, passes);
    `skip_empty`: items with no entries make none (SHADE's lists)."""
    out = []
    for own in deal:
        kept = []
        for index in own:
            if skip_empty and items[index][3] == 0:
                continue
            kept.append((index, item_passes(sets, across, items[index], unit, slots)))
        out.append(kept)
    return out


def kept_reads(passes, caches, slots):
    """Pages read when each core keeps its slots (least recently used out) across its
    passes, `caches` a core's OrderedDict kept between calls: (reads, asked)."""
    reads = asked = 0
    for core, own in enumerate(passes):
        cache = caches[core]
        for _, item in own:
            for one in item:
                asked += len(one)
                for page in one:
                    if page in cache:
                        cache.move_to_end(page)
                    else:
                        reads += 1
                        cache[page] = True
                while len(cache) > slots:
                    cache.popitem(last=False)
    return reads, asked


def new_caches(cores):
    """Empty slots of `cores` cores."""
    return [OrderedDict() for _ in range(cores)]


def today(passes):
    """Pages asked and passes, the slots emptied at every pass."""
    pages = sum(len(one) for own in passes for _, item in own for one in item)
    count = sum(len(item) for own in passes for _, item in own)
    return {"pages": pages, "passes": count}


def figures(values):
    """Mean, median, 99th percentile and most of a list of numbers."""
    values = np.asarray(values, dtype=np.float64)
    if len(values) == 0:
        return {"n": 0}
    return {
        "n": len(values),
        "mean": round(float(values.mean()), 3),
        "median": float(np.median(values)),
        "p99": float(np.percentile(values, 99)),
        "most": float(values.max()),
    }


def item_shapes(passes, decode):
    """An item's distinct pages and their bounding boxes: `decode(pages)` gives per page
    its group and grid coordinates (group, (n, 3)); the box a group, summed."""
    distinct, boxes, read = [], [], []
    for own in passes:
        for _, item in own:
            pages = np.array(sorted(set().union(*item)), dtype=np.int64)
            distinct.append(len(pages))
            if len(pages) == 0:
                continue
            group, at = decode(pages)
            box = 0
            for one in np.unique(group):
                mine = at[group == one]
                box += int(np.prod(mine.max(axis=0) - mine.min(axis=0) + 1))
            boxes.append(box)
            read.append(len(pages) / box)
    boxes = np.asarray(boxes)
    return {
        "items": len(distinct),
        "pages": figures(distinct),
        "items_with_pages": len(boxes),
        "box_pages": figures(boxes),
        "box_share_read": figures(read),
        "box_share_read_pooled": round(
            float(np.sum(distinct) / max(boxes.sum(), 1)), 4
        ),
        "items_box_at_most": {
            str(n): round(float((boxes <= n).mean()), 4) if len(boxes) else 0.0
            for n in RECTANGLES
        },
    }


def item_block(values, item):
    """An item's pixels of values (H, W, K, D): (rows, 32 K, D)."""
    tile, first_row, end_row = item[:3]
    across = values.shape[1] // TILE
    tx, ty = tile % across, tile // across
    rows = slice(TILE * ty + first_row, TILE * ty + end_row)
    block = values[rows, TILE * tx : TILE * (tx + 1)]
    return block.reshape(block.shape[0], -1, values.shape[-1]).astype(np.int64)


def item_values(values, item):
    """The values (n, D) of an item's pixels (values (H, W, K, D)) that name a texel."""
    block = item_block(values, item).reshape(-1, values.shape[-1])
    return block[block[:, 0] >= 0]


def row_values(values, items):
    """Each row of 32 pixels of the items: its values (n, D) that name a texel, for the
    rows with any."""
    for item in items:
        for row in item_block(values, item):
            row = row[row[:, 0] >= 0]
            if len(row):
                yield row


def share(flags):
    """The share of true values, 0 of none."""
    return round(float(np.mean(flags)), 4) if len(flags) else 0.0


def distinct_rows(values):
    """The distinct rows of an integer array (n, D)."""
    return np.unique(values, axis=0) if len(values) else values


def tap_extent(items, taps, sides=(32, 64, 128, 256)):
    """An item's shadow taps in texels of the map: its rectangle's width, height and
    texels, the share of items within side x side, the share of the rectangle read."""
    width, height, read = [], [], []
    for item in items:
        at = item_values(taps, item)
        if len(at) == 0:
            continue
        w, h = at.max(axis=0) - at.min(axis=0) + 1
        width.append(w)
        height.append(h)
        read.append(len(distinct_rows(at)) / (w * h))
    width, height = np.asarray(width), np.asarray(height)
    rows = [r.max(axis=0) - r.min(axis=0) + 1 for r in row_values(taps, items)]
    rows = np.asarray(rows).reshape(-1, 2)
    return {
        "items_with_taps": len(width),
        "width": figures(width),
        "height": figures(height),
        "texels": figures(width * height),
        "items_within": {
            f"{n}x{n}": share((width <= n) & (height <= n)) for n in sides
        },
        "share_read": figures(read),
        "row_width": figures(rows[:, 0]),
        "row_height": figures(rows[:, 1]),
    }


def voxel_extent(items, voxels, counts=(64, 128, 256, 512, 1024)):
    """An item's field corners in voxels: its box along x, y, z and its voxels, its
    distinct voxels, the share of items with at most n of them, the share read."""
    boxes, distinct, read = [], [], []
    for item in items:
        at = item_values(voxels, item)
        if len(at) == 0:
            continue
        box = at.max(axis=0) - at.min(axis=0) + 1
        boxes.append(box)
        distinct.append(len(distinct_rows(at)))
        read.append(distinct[-1] / int(np.prod(box)))
    boxes, distinct = np.asarray(boxes).reshape(-1, 3), np.asarray(distinct)
    return {
        "items_with_voxels": len(distinct),
        "box": {axis: figures(boxes[:, k]) for k, axis in enumerate("xyz")},
        "box_voxels": figures(np.prod(boxes, axis=1)),
        "distinct": figures(distinct),
        "items_at_most": {str(n): share(distinct <= n) for n in counts},
        "share_read": figures(read),
    }


def texel_extent(layer_items, sides=(32, 64, 128)):
    """An item's texture reads: its distinct (texture, level) pairs and, per pair, its
    rectangle in texels of that level; the share of pairs within side x side, pooled
    over every item's pairs and as the mean of an item's share."""
    pairs, fits, item_share = [], {n: [] for n in sides}, {n: [] for n in sides}
    for items, texels in layer_items:
        for item in items:
            at = item_values(texels, item)
            if len(at) == 0:
                continue
            groups = np.unique(at[:, 0])
            pairs.append(len(groups))
            sizes = np.array(
                [np.ptp(at[at[:, 0] == g, 1:], axis=0) + 1 for g in groups]
            )
            for n in sides:
                within = (sizes <= n).all(axis=1)
                fits[n] += within.tolist()
                item_share[n].append(within.mean())
    return {
        "items_with_texels": len(pairs),
        "pairs": figures(pairs),
        "pairs_within": {f"{n}x{n}": share(fits[n]) for n in sides},
        "item_share_within": {
            f"{n}x{n}": round(float(np.mean(item_share[n])), 4) if pairs else 0.0
            for n in sides
        },
    }


def cell_extent(items, cells):
    """The field lookup's cells: the distinct cells an item's pixels fall in, and a row
    of 32 pixels' with the share of rows with 1, at most 2 and at most 4."""
    per_item = [len(distinct_rows(item_values(cells, item))) for item in items]
    per_item = [n for n in per_item if n]
    per_row = np.array([len(distinct_rows(r)) for r in row_values(cells, items)])
    return {
        "item_cells": figures(per_item),
        "row_cells": figures(per_row),
        "rows_with": {
            "1": share(per_row == 1),
            "at_most_2": share(per_row <= 2),
            "at_most_4": share(per_row <= 4),
        },
    }


def working_set(passes):
    """The distinct pages each core reads in a frame over all its items: median and
    most over the cores."""
    sizes = [
        len(set().union(*(one for _, item in own for one in item))) for own in passes
    ]
    return {"median": float(np.median(sizes)), "most": int(max(sizes))}
