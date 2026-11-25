"""The middle pass's C built with host gcc and run against the model: on the scenes'
counters, on seeded hot tiles and at 8,160 tiles; and setup.h's sizes built with g++."""

import ctypes
import subprocess
import time

import numpy as np

from checks.raster_model.compare import asserted
from checks.raster_model.model import CORES
from prism.core import capacity as p_capacity
from prism.stages.raster import capacity as p_stage
from prism.stages.raster.model import bands, middle, numbers
from prism_common.paths import build_root

THREAD = numbers.THREAD
SOURCES = ("raster_middle.c", "raster_middle_whole.c")
HEAVY_MOST = 1024  # the heavy tiles' arrays given to rm_heavy
# the capacities whose setup.h sizes are built: (tiles, recount, fill cores)
SETUP_CAPACITIES = (
    (32, False, CORES),
    (928, False, CORES),
    (1024, False, CORES),
    (2048, False, CORES),
    (3616, False, CORES),
    (8160, False, CORES),
    (3616, True, CORES),
    (8160, True, CORES),
    (8160, True, 140),
    (1024, False, None),
)


def build(tiles, heavy, band_items):
    """The two C files built with host gcc into the build root, as a library."""
    out = build_root() / f"raster_middle_{tiles}_{heavy}_{band_items}.so"
    command = ["gcc", "-std=c11", "-O2", "-Wall", "-Werror", "-shared", "-fPIC"]
    command += [f"-DRM_TILES={tiles}u", f"-DRM_MAX_HEAVY={heavy}u"]
    command += [f"-DRM_BAND_ITEMS={band_items}u"]
    command += [f"-I{THREAD}", f"-I{numbers.INCLUDE}"]
    sources = [str(THREAD / source) for source in SOURCES]
    subprocess.run([*command, *sources, "-o", str(out)], check=True)
    library = ctypes.CDLL(str(out))
    pointer, word = ctypes.c_void_p, ctypes.c_uint32
    library.rm_heavy.argtypes = [pointer, word, word, pointer, pointer, pointer]
    library.rm_heavy.restype = word
    library.rm_middle.argtypes = [pointer, pointer, word, word, pointer, pointer, word]
    library.rm_middle.argtypes += [*[pointer] * 8, word]
    library.rm_middle.restype = word
    library.rm_compact.argtypes = [word, pointer, pointer, word, pointer, pointer]
    library.rm_compact.restype = word
    library.rm_base.argtypes = [pointer, pointer, word, pointer]
    library.rm_base.restype = None
    return library


def c_step(library, counts, rows, first, last, fill, tiles=1024, band_items=1024):
    """rm_heavy, rm_middle, rm_compact and rm_base of a library built for `tiles` and
    `band_items` on the counts (setup cores, tiles) and histograms; their outputs."""
    setup_cores = len(counts)
    most = tiles + band_items
    counters = np.concatenate([counts, rows], axis=1)
    counters = np.ascontiguousarray(counters, dtype=np.uint32)
    scratch = np.zeros(16 << 20, dtype=np.uint8)
    heavy = np.zeros(HEAVY_MOST, dtype=np.uint32)
    bands_of = np.zeros(HEAVY_MOST, dtype=np.uint32)
    found = library.rm_heavy(
        counters.ctypes.data,
        setup_cores,
        fill,
        scratch.ctypes.data,
        heavy.ctypes.data,
        bands_of.ctypes.data,
    )
    hot = heavy[: min(found, HEAVY_MOST)].astype(int)
    # (setup cores, heavy tiles, 32): the starts, then the ends, per 2-row group
    hist = np.concatenate([first[:, hot], last[:, hot]], axis=2)
    hist = np.ascontiguousarray(hist, dtype=np.uint16)
    items = np.zeros((most, 4), dtype=np.uint32)
    tile_item = np.zeros(tiles + 1, dtype=np.uint32)
    directory = np.zeros((fill, numbers.K["kDirBytes"] // 4), dtype=np.uint32)
    marks = np.zeros((most + numbers.M["RM_MAX_CORES"], 6), dtype=np.uint32)
    next_slot = np.zeros((setup_cores, most), dtype=np.uint32)
    item_total, mark_total = ctypes.c_uint32(), ctypes.c_uint32()
    slots = library.rm_middle(
        counters.ctypes.data,
        hist.ctypes.data,
        setup_cores,
        fill,
        heavy.ctypes.data,
        bands_of.ctypes.data,
        found,
        scratch.ctypes.data,
        items.ctypes.data,
        ctypes.addressof(item_total),
        tile_item.ctypes.data,
        directory.ctypes.data,
        marks.ctypes.data,
        ctypes.addressof(mark_total),
        next_slot.ctypes.data,
        most,
    )
    item_count = item_total.value
    item_words = np.zeros((most, 2), dtype=np.uint32)
    core_words = np.zeros((fill, 4), dtype=np.uint32)
    compact = library.rm_compact(
        fill,
        scratch.ctypes.data,
        items.ctypes.data,
        item_count,
        item_words.ctypes.data,
        core_words.ctypes.data,
    )
    base = np.zeros(most, dtype=np.uint32)
    library.rm_base(
        scratch.ctypes.data, items.ctypes.data, item_count, base.ctypes.data
    )
    return {
        "found": found,
        "heavy": list(zip(hot.tolist(), bands_of[: len(hot)].tolist())),
        "hist": hist,
        "items": items[:item_count],
        "tile_item": tile_item,
        "directory": directory,
        "marks": marks[: mark_total.value],
        "next": next_slot[:, :item_count],
        "slots": slots,
        "compact": (compact, item_words[:item_count], core_words),
        "base": base[:item_count],
    }


def from_prefixes(result, counts):
    """Each setup core's next slots as SETUP makes them from the base words and SUM's
    and HSUM's prefixes."""
    bits = numbers.S["kBaseSlotBits"]
    slot = result["base"] & ((1 << bits) - 1)
    band = result["base"] >> bits
    before = np.cumsum(counts, axis=0) - counts
    hist = result["hist"].astype(np.int64)
    hist_before = np.cumsum(hist, axis=0) - hist
    starts = np.cumsum(hist_before[:, :, : numbers.GROUPS], axis=2)
    ends = np.cumsum(hist_before[:, :, numbers.GROUPS :], axis=2)
    out = np.zeros((len(counts), len(slot)), dtype=np.int64)
    for i, (tile, first_row, end_row) in enumerate(result["items"][:, :3].tolist()):
        if band[i] == 0:
            out[:, i] = slot[i] + before[:, tile]
            continue
        end_group, first_group = end_row // 2, first_row // 2
        started = starts[:, band[i] - 1, end_group - 1] if end_group else 0
        ended = ends[:, band[i] - 1, first_group - 1] if first_group else 0
        out[:, i] = slot[i] + started - ended
    return out


def header_pages(slots, marks):
    """List slots holding the headers and end slots of `marks`: (slot, mark, tile,
    records, first_row, end_row) each."""
    k = numbers.K
    pages = np.zeros((slots, numbers.SLOT), dtype=np.uint32)
    columns = [0, k["kHdrTile"], k["kHdrCount"], k["kHdrRow0"], k["kHdrRow1"]]
    for slot, mark, tile, total, first_row, end_row in marks:
        pages[slot, 0] = mark
        if mark == k["kMarkTile"]:
            pages[slot, columns] = mark, tile, total, first_row, end_row
    return pages


def placed(result, slots):
    """The directory pages and list headers PLACE makes from rm_compact's words."""
    k = numbers.K
    _, item_words, core_words = result["compact"]
    directory = np.zeros((len(core_words), k["kDirBytes"] // 4), dtype=np.uint32)
    marks = []
    for core, (first, pages, item_count, end) in enumerate(core_words.tolist()):
        directory[core, : k["kDirIds"]] = first, pages, item_count
        marks.append((end, k["kMarkEnd"], 0, 0, 0, 0))
    cursor = np.zeros(len(core_words), dtype=int)
    for (word, slot), (tile, first_row, end_row, total) in zip(
        item_words.tolist(), result["items"].tolist()
    ):
        core, entries = word & 0xFF, word >> 8
        item_id = tile
        if (first_row, end_row) != (0, 32):
            item_id |= first_row << k["kItemRow0Shift"]
            item_id |= end_row << k["kItemRow1Shift"]
        if not total:
            item_id |= k["kItemEmpty"]
        directory[core, k["kDirIds"] + cursor[core]] = item_id
        cursor[core] += 1
        if total:
            marks.append((slot, k["kMarkTile"], tile, entries, first_row, end_row))
    return directory, header_pages(slots, marks)


def c_case(name, library, counts, rows, first, last, fill):
    """The C step against the model's middle pass on the same counts."""
    started = time.perf_counter()
    result = c_step(library, counts, rows, first, last, fill)
    heavy = bands.heavy_tiles(counts, rows, fill)
    hot = [tile for tile, _ in heavy]
    made = bands.items_of(counts, rows, heavy, first[:, hot], last[:, hot])
    mid = middle.middle(counts, rows, fill, bands=made)
    shape = mid["pages"].shape
    marked = header_pages(mid["slots"], result["marks"].tolist())
    directory, pages = placed(result, mid["slots"])
    tile_item = result["tile_item"]
    first_and_count = tile_item[:-1] | (np.diff(tile_item) << 16)
    items_page = middle.item_table(mid["items"])[: numbers.TILES]
    items = [tuple(item[:3]) for item in result["items"].tolist()]
    conditions = [
        ("heavy tiles", result["heavy"] == heavy),
        ("items", items == mid["items"]),
        ("item totals", np.array_equal(result["items"][:, 3], made[1].sum(0))),
        ("directory", np.array_equal(result["directory"], mid["directory"])),
        ("slots", result["slots"] == mid["slots"]),
        ("next slots", np.array_equal(result["next"], mid["next"])),
        (
            "next slots from the prefixes",
            np.array_equal(from_prefixes(result, counts), mid["next"]),
        ),
        ("headers and end slots", np.array_equal(marked.reshape(shape), mid["pages"])),
        ("rm_compact's slots", result["compact"][0] == mid["slots"]),
        ("PLACE's directory", np.array_equal(directory, mid["directory"])),
        ("PLACE's headers", np.array_equal(pages.reshape(shape), mid["pages"])),
        ("the items page", np.array_equal(first_and_count, items_page)),
    ]
    asserted(
        f"{name}: C middle pass, {fill} fill cores, {len(heavy)} heavy tiles",
        conditions,
        started,
    )


def hot_counts():
    """Counters and histograms of 7 cores whose entries are mostly in three tiles
    (seeded)."""
    rng = np.random.default_rng(5)
    cores, entry_count, tiles = 7, 6000, numbers.TILES
    core = rng.integers(0, cores, entry_count)
    tile = np.where(
        rng.random(entry_count) < 0.7,
        rng.choice([5, 400, 401], entry_count),
        rng.integers(0, tiles, entry_count),
    )
    first_row = rng.integers(0, 32, entry_count)
    last_row = np.minimum(31, first_row + rng.integers(0, 12, entry_count))
    base = (core * tiles + tile) * numbers.GROUPS
    shape = (cores, tiles, numbers.GROUPS)
    size = cores * tiles * numbers.GROUPS
    first = np.bincount(base + first_row // 2, minlength=size).reshape(shape)
    last = np.bincount(base + last_row // 2, minlength=size).reshape(shape)
    cell = core * tiles + tile
    counts = np.bincount(cell, minlength=cores * tiles).reshape(cores, tiles)
    rows = np.bincount(cell, last_row - first_row + 1, minlength=cores * tiles)
    return counts, rows.reshape(cores, tiles).astype(np.int64), first, last


def large_cases():
    """8,160 tiles: 301 heavy tiles past the 256-tile table and within the table of
    120 fill cores; a directory page full."""
    started = time.perf_counter()
    tiles = 8160
    stepped_heavy, stepped_items = p_stage.heavy_capacity(None)
    heavy, band_items = p_stage.heavy_capacity(
        p_capacity.Capacity(tiles, True, False, CORES)
    )
    stepped = build(tiles, stepped_heavy, stepped_items)
    sized = build(tiles, heavy, band_items)
    # 300 tiles just above a third of a core's mean, one above the mean
    loaded = np.zeros((1, tiles), dtype=np.int64)
    loaded[0, :300] = 3820
    loaded[0, 300] = 38440
    # 356 tiles of 4 M, none cut, and empty tiles: the least loaded cores fill up
    full = np.zeros((1, tiles), dtype=np.int64)
    full[0, :356] = 15358
    hist = np.zeros((1, tiles, numbers.GROUPS), dtype=np.int64)
    rows = np.zeros((1, tiles), dtype=np.int64)
    small = c_step(stepped, loaded, rows, hist, hist, CORES, tiles, stepped_items)
    big = c_step(sized, loaded, rows, hist, hist, CORES, tiles, band_items)
    whole = c_step(sized, full, rows, hist, hist, CORES, tiles, band_items)
    own = whole["directory"][:, numbers.K["kDirItems"]]
    conditions = [
        (
            "the 256-tile table refuses 301 heavy tiles",
            (small["found"], small["slots"]) == (301, 0),
        ),
        ("the sized table lays them out", big["found"] == 301 and big["slots"] > 0),
        ("their items", tiles < len(big["items"]) <= tiles + band_items),
        ("full page: no tile cut", whole["found"] == 0),
        ("full page: every tile an item", len(whole["items"]) == tiles),
        ("full page: laid out", whole["slots"] > 0),
        ("a page holds kDirMaxItems at most", own.max() == numbers.K["kDirMaxItems"]),
        ("every item owned", own.sum() == tiles),
    ]
    asserted(
        "8,160 tiles: C past 256 heavy tiles, a directory page full",
        conditions,
        started,
    )


def setup_sizes_case():
    """setup.h's sizes built with host g++ at each capacity against numbers.sizes."""
    started = time.perf_counter()
    names = sorted(numbers.sizes(1024, False, 256, 1024))
    prints = " ".join(f'printf("%u\\n", (unsigned){name});' for name in names)
    source = build_root() / "raster_setup_sizes.cpp"
    source.write_text(
        f'#include <cstdio>\n#include "setup.h"\nint main() {{ {prints} }}\n'
    )
    out = build_root() / "raster_setup_sizes"
    conditions = []
    for tiles, recount, cores in SETUP_CAPACITIES:
        held = p_capacity.Capacity(tiles, True, recount, cores)
        heavy, band_items = p_stage.heavy_capacity(held)
        flags = ["-std=c++17", f"-I{numbers.KERNELS}", f"-I{numbers.INCLUDE}"]
        flags += [f"-DRASTER_TILES={tiles}", f"-DRASTER_HEAVY={heavy}"]
        flags += [f"-DRASTER_BAND_ITEMS={band_items}"]
        if recount:
            flags.append("-DRASTER_RECOUNT=1")
        subprocess.run(["g++", *flags, str(source), "-o", str(out)], check=True)
        run = subprocess.run([str(out)], check=True, capture_output=True, text=True)
        got = dict(zip(names, (int(n) for n in run.stdout.split()), strict=True))
        want = numbers.sizes(tiles, recount, heavy, band_items)
        conditions.append(
            (f"{tiles} tiles, recount {recount}, {cores} cores", got == want)
        )
    asserted("setup.h's sizes built with g++ equal numbers.sizes", conditions, started)
