"""The tile threads' data in numpy: the slices of a grid, and a view's layout as the
count, sums and place kinds and the frame's thread leave it, in record.h's words."""

import itertools
import re

import numpy as np

from prism.core.headers import INCLUDE, defined
from prism.stages.raster.model.bands import band_count, cuts
from prism.stages.raster.model.numbers import GROUPS, LANES, MAX_BANDS
from prism.stages.raster.model.records import pack_records
from prism_reference.raster.setup import grid, setup
from prism_reference.scene.frame import TILE

RECORD_H = INCLUDE / "thread" / "record.h"
R = defined(RECORD_H)
TR_LAYERS, TR_WORDS, TS_WORDS = R["TR_LAYERS"], R["TR_WORDS"], R["TS_WORDS"]
RANGE_BLOCKS = 4  # the triangle blocks a count range holds, unless given
ROWS = 2 * GROUPS  # a tile's rows
MACRO = re.compile(
    r"^#define\s+(\w+)\(([\w,\s]+)\)\s+(.+?)\s*(?:/\*.*)?$", re.MULTILINE
)
LITERAL = re.compile(r"\b(0x[0-9A-Fa-f]+|\d+)u\b")


def macros(path, **build):
    """{name: function} of every function-like `#define` of the header at `path`, its
    body evaluated over the header's own numbers and the build defines `build`."""
    numbers = defined(path) | build
    out = {}
    for name, arguments, body in MACRO.findall(path.read_text()):
        expression = (
            LITERAL.sub(r"\1", body).replace("(uint32_t)", "").replace("/", "//")
        )
        source = f"lambda {arguments}: {expression}"
        out[name] = eval(source, {"__builtins__": {}, **numbers})
    return out


M = macros(RECORD_H)  # TR_NUMBER and its inverses need the build define: `macros`


def word0(tile, first_row, end_row):
    """A record's word 0 (record.h): tile | first_row << 16 | end_row << 24."""
    return int(tile) | int(first_row) << 16 | int(end_row) << 24


def slices(grid, slice_tiles):
    """The slices of a grid (across, down): runs of `slice_tiles` neighbouring tiles
    along a row, the last of a row shorter, row by row. {tiles: each slice's tiles,
    of: each tile's slice, grid: (slices across, down)}."""
    across, down = (int(n) for n in grid)
    if slice_tiles < 1:
        raise ValueError(f"slices: {slice_tiles} tiles a slice; at least 1")
    per_row = -(-across // slice_tiles)
    tiles = [
        row * across + np.arange(x, min(x + slice_tiles, across))
        for row in range(down)
        for x in range(0, across, slice_tiles)
    ]
    column = np.arange(across * down) % across
    of = (np.arange(across * down) // across) * per_row + column // slice_tiles
    return {"tiles": tiles, "of": of.astype(np.int64), "grid": (per_row, down)}


def layers_of(scene, view):
    """(name, scene) of each layer under the view's camera and size: `scene` one scene
    dict (one layer) or (name, scene, ...) a layer."""
    given = [("scene", scene)] if isinstance(scene, dict) else scene
    given = [(one[0], one[1]) for one in given]
    if not 1 <= len(given) <= TR_LAYERS:
        raise ValueError(f"layout: {len(given)} layers; 1 to {TR_LAYERS}")
    kept = {key: view[key] for key in ("camera", "size") if key in (view or {})}
    return [(name, {**one, **kept}) for name, one in given]


def range_cores(log, total, cores):
    """The core that counted each of the view's `total` ranges, and the cores: `log`
    a core a range (None: core 0 for every range); `cores` None: the log's highest + 1.
    """
    if log is None:
        log = np.zeros(total, dtype=np.int64)
    log = np.asarray(log, dtype=np.int64).reshape(-1)
    if len(log) != total:
        raise ValueError(f"layout: a log of {len(log)} ranges; the view has {total}")
    cores = int(log.max(initial=0)) + 1 if cores is None else int(cores)
    if len(log) and (log.min() < 0 or log.max() >= cores):
        raise ValueError(f"layout: a log names a core outside 0 to {cores - 1}")
    return log, cores


def entries(pieces, across, core_of_range, first_range, range_blocks):
    """Every (piece, tile) entry in piece order: the piece, its tile, the core that
    took its triangle's range, its first and last row inside the tile."""
    box = pieces["box"].astype(np.int64)
    first_x, last_x = box[:, 0] // TILE, box[:, 1] // TILE
    first_y, last_y = box[:, 2] // TILE, box[:, 3] // TILE
    wide, high = last_x - first_x + 1, last_y - first_y + 1
    per_piece = wide * high
    piece = np.repeat(np.arange(len(box)), per_piece)
    local = np.arange(per_piece.sum()) - np.repeat(
        np.cumsum(per_piece) - per_piece, per_piece
    )
    tile_y = first_y[piece] + local // wide[piece]
    tile = tile_y * across + first_x[piece] + local % wide[piece]
    top = TILE * tile_y
    ranges = pieces["tri"].astype(np.int64) // LANES // range_blocks
    return {
        "piece": piece,
        "tile": tile,
        "core": core_of_range[first_range + ranges[piece]],
        "first_row": np.maximum(box[piece, 2], top) - top,
        "last_row": np.minimum(box[piece, 3], top + TILE - 1) - top,
    }


def counted(table, cores, tiles):
    """What count leaves a core for a layer: its entries a tile (cores, tiles), and its
    row histograms: entries starting, and ending, in each 2-row group (cores, tiles,
    GROUPS) twice."""
    cell = table["core"] * tiles + table["tile"]
    counts = np.bincount(cell, minlength=cores * tiles).reshape(cores, tiles)
    shape, size = (cores, tiles, GROUPS), cores * tiles * GROUPS
    starts = np.bincount(cell * GROUPS + table["first_row"] // 2, minlength=size)
    ends = np.bincount(cell * GROUPS + table["last_row"] // 2, minlength=size)
    return counts, starts.reshape(shape), ends.reshape(shape)


def items_of(counts, starts, ends, heavy):
    """The items in tile order (tile, first_row, end_row) and each item's entries a
    layer and core (items, layers, cores): a tile whose entries over every layer pass
    `heavy` (None: none) cut into min(MAX_BANDS, ceil(weight / heavy)) bands by
    `bands.cuts` over every core's and layer's row histograms."""
    weight = sum(layer.sum(0) for layer in counts)
    items, per = [], []
    for tile in range(len(weight)):
        if heavy is None or weight[tile] <= heavy:
            items.append((tile, 0, ROWS))
            per.append(np.stack([layer[:, tile] for layer in counts]))
            continue
        tile_starts = np.stack([layer[:, tile] for layer in starts])
        tile_ends = np.stack([layer[:, tile] for layer in ends])
        bands = min(MAX_BANDS, -(-int(weight[tile]) // int(heavy)))
        bounds = cuts(tile_starts.sum((0, 1)), tile_ends.sum((0, 1)), bands)
        for first_row, end_row in itertools.pairwise(bounds):
            items.append((tile, int(first_row), int(end_row)))
            per.append(band_count(tile_starts, tile_ends, first_row, end_row))
    return np.asarray(items, dtype=np.int64), np.stack(per).astype(np.int64)


def summed(items, per, sliced, slice_records, page):
    """What the sums write: each core's first position in each item's list, from its
    slice's place (layers, cores, items); the records a slice in order of weight
    (slices * slice_records, TR_WORDS); the slices' words without their places."""
    count = len(sliced["tiles"])
    number = macros(RECORD_H, TR_SLICE_RECORDS=slice_records)["TR_NUMBER"]
    layers, cores = per.shape[1], per.shape[2]
    entries = per.sum(2)  # (items, layers)
    weight = entries.sum(1)
    of = sliced["of"][items[:, 0]]
    positions = np.zeros((layers, cores, len(items)), dtype=np.int64)
    records = np.zeros((count * slice_records, TR_WORDS), dtype=np.uint32)
    words = np.zeros((count, TS_WORDS), dtype=np.uint32)
    for s in range(count):
        own = np.flatnonzero(of == s)
        if len(own) > slice_records:
            raise ValueError(
                f"sums: slice {s} has {len(own)} records; it holds {slice_records}"
            )
        start = np.cumsum(entries[own], axis=0) - entries[own]  # (own, layers)
        before = np.cumsum(per[own], axis=2) - per[own]  # (own, layers, cores)
        positions[:, :, own] = (start[:, :, None] + before).transpose(1, 2, 0)
        for place, mine in enumerate(np.argsort(-weight[own], kind="stable")):
            item = own[mine]
            tile, first_row, end_row = items[item]
            row = records[number(s, place)]
            row[0] = word0(tile, first_row, end_row)
            row[1] = weight[item]
            row[2] = sum(1 << layer for layer in range(layers) if entries[item, layer])
            row[3] = page + tile
            for layer in range(layers):
                row[M["TR_LAYER_SLOT"](layer)] = start[mine, layer]
                row[M["TR_LAYER_ENTRIES"](layer)] = entries[item, layer]
        words[s, R["TS_RECORDS"]] = len(own)
        words[s, R["TS_WEIGHT"]] = weight[own].sum()
        for layer in range(layers):
            words[s, M["TS_ENTRIES"](layer)] = entries[own, layer].sum()
    return positions, records, words


def placed(words, layers):
    """The frame's thread's running sum over the slices, a layer: each slice's place,
    written into the slices' words at TS_PLACE (a copy); the places (slices, layers)."""
    out = words.copy()
    places = np.zeros((len(words), layers), dtype=np.int64)
    for layer in range(layers):
        sizes = words[:, M["TS_ENTRIES"](layer)].astype(np.int64)
        places[:, layer] = np.cumsum(sizes) - sizes
        out[:, M["TS_PLACE"](layer)] = places[:, layer]
    return out, places


def item_index(items, tiles):
    """Each tile's first item and its items (tiles,) twice."""
    first = np.searchsorted(items[:, 0], np.arange(tiles))
    return first.astype(np.int64), np.bincount(items[:, 0], minlength=tiles)


def place_layer(table, packed, items, positions, slice_place, item_first, item_count):
    """What place writes of a layer: each entry to the list of each item of its tile
    its rows reach, at its core's running position there. (slots (n, SLOT) uint32,
    the piece in each slot (n,) int64); ValueError on a slot written twice."""
    reach = item_count[table["tile"]]
    entry = np.repeat(np.arange(len(table["tile"])), reach)
    local = np.arange(reach.sum()) - np.repeat(np.cumsum(reach) - reach, reach)
    item = item_first[table["tile"]][entry] + local
    keep = (table["first_row"][entry] < items[item, 2]) & (
        table["last_row"][entry] >= items[item, 1]
    )
    entry, item = entry[keep], item[keep]
    core = table["core"][entry]
    key = core * len(items) + item
    order = np.argsort(key, kind="stable")
    group_start = np.searchsorted(key[order], key[order], side="left")
    rank = np.empty(len(order), dtype=np.int64)
    rank[order] = np.arange(len(order)) - group_start
    slot = slice_place[item] + positions[core, item] + rank
    total = len(slot)
    if total and (slot.min() < 0 or slot.max() >= total):
        raise ValueError(f"place: a slot outside the layer's {total} entries")
    if np.bincount(slot, minlength=total).max(initial=0) > 1:
        raise ValueError("place: a list slot written twice")
    pieces = np.full(total, -1, dtype=np.int64)
    pieces[slot] = table["piece"][entry]
    return packed[np.maximum(pieces, 0)], pieces


def layout(
    scene,
    view,
    log,
    slice_tiles,
    heavy,
    range_blocks=RANGE_BLOCKS,
    cores=None,
    slice_records=None,
):
    """A view's layout: `scene` one scene or its layers; `view` {camera, size, page:
    the target's first page}; `log` the core that counted each range (None: one core);
    a tile past `heavy` entries cut into bands; `slice_records` TR_SLICE_RECORDS (None:
    the most a slice has). The lists, positions, items, records and slices' words."""
    named = layers_of(scene, view)
    across, down = grid(named[0][1])
    tiles = across * down
    pieces = [setup(one) for _, one in named]
    triangles = [len(one["indices"]) for _, one in named]
    blocks = [-(-n // LANES) for n in triangles]
    ranges = np.asarray([-(-n // range_blocks) for n in blocks], dtype=np.int64)
    first_range = np.cumsum(ranges) - ranges
    core_of_range, cores = range_cores(log, int(ranges.sum()), cores)
    tables, counts, starts, ends = [], [], [], []
    for layer, one in enumerate(pieces):
        table = entries(one, across, core_of_range, first_range[layer], range_blocks)
        tables.append(table)
        layer_counts, layer_starts, layer_ends = counted(table, cores, tiles)
        counts.append(layer_counts)
        starts.append(layer_starts)
        ends.append(layer_ends)
    sliced = slices((across, down), slice_tiles)
    items, per = items_of(counts, starts, ends, heavy)
    item_first, item_count = item_index(items, tiles)
    most = int(np.bincount(sliced["of"][items[:, 0]]).max())
    slice_records = most if slice_records is None else int(slice_records)
    page = int((view or {}).get("page", 0))
    positions, records, words = summed(items, per, sliced, slice_records, page)
    words, places = placed(words, len(named))
    lists = []
    for layer, one in enumerate(pieces):
        slice_place = places[sliced["of"][items[:, 0]], layer]
        slots, by_slot = place_layer(
            tables[layer],
            pack_records(one),
            items,
            positions[layer],
            slice_place,
            item_first,
            item_count,
        )
        lists.append({"slots": slots, "pieces": by_slot})
    return {
        "layers": [name for name, _ in named],
        "grid": (across, down),
        "cores": cores,
        "pieces": pieces,
        "ranges": {"first": first_range, "count": ranges, "cores": core_of_range},
        "counts": counts,
        "starts": starts,
        "ends": ends,
        "slices": sliced,
        "items": items,
        "item_first": item_first,
        "item_count": item_count,
        "item_entries": per,
        "positions": positions,
        "slice_records": slice_records,
        "records": records,
        "slice_words": words,
        "places": places,
        "lists": lists,
    }


def item_table(laid):
    """The items' table the place kind reads: per tile its first item | its items
    << 16, then per item its rows first_row | end_row << 8 (tiles + items,) uint32."""
    rows = laid["items"][:, 1] | laid["items"][:, 2] << 8
    head = laid["item_first"] | laid["item_count"] << 16
    return np.concatenate([head, rows]).astype(np.uint32)


def positions_words(laid):
    """Each core's first positions a layer, from its slice's place: a row of the items
    a core (layers, cores, items) uint32."""
    return laid["positions"].astype(np.uint32)
