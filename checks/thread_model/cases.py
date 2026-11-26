"""The cases of the tile threads' model: record.h's words, every list against the
reference's binning, a random log's lists and records, the bands, the slices' places."""

import itertools
import time

import numpy as np

from checks.raster_model.compare import asserted
from prism.stages.raster.model import threads
from prism.stages.raster.model.numbers import GROUPS
from prism.stages.raster.model.records import pack_records
from prism.stages.raster.model.threads import RECORD_H, TR_LAYERS, G, M, R, macros
from prism_reference.raster.fill import bin_triangles
from prism_reference.scene.frame import TILE

CORES = 120  # the random log's cores
SEED = 11


def words_case():
    """`word0` read back by TR_TILE, TR_FIRST_ROW, TR_END_ROW; TR_NUMBER read back by
    TR_SLICE_OF and TR_PLACE_OF; the layers' words inside a record and a slice."""
    started = time.perf_counter()
    numbered = macros(RECORD_H, TR_SLICE_RECORDS=37)
    samples = [(0, 0, 32), (2039, 6, 18), (65535, 30, 32)]
    back = [
        (M["TR_TILE"](w), M["TR_FIRST_ROW"](w), M["TR_END_ROW"](w))
        for w in (threads.word0(*one) for one in samples)
    ]
    pairs = [(s, p) for s in (0, 5, 400) for p in (0, 36)]
    numbers = [numbered["TR_NUMBER"](s, p) for s, p in pairs]
    record_words = [M["TR_LAYER_SLOT"](n) for n in range(TR_LAYERS)]
    record_words += [M["TR_LAYER_ENTRIES"](n) for n in range(TR_LAYERS)]
    slice_words = [R["TS_RECORDS"], R["TS_WEIGHT"]]
    slice_words += [M["TS_ENTRIES"](n) for n in range(TR_LAYERS)]
    slice_words += [M["TS_PLACE"](n) for n in range(TR_LAYERS)]
    conditions = [
        ("word 0 read back", back == samples),
        (
            "number read back",
            [(numbered["TR_SLICE_OF"](n), numbered["TR_PLACE_OF"](n)) for n in numbers]
            == pairs,
        ),
        ("record's layer words", sorted(record_words) == list(range(4, 12))),
        ("record's words fit", max(record_words) < R["TR_WORDS"]),
        ("slice's words distinct", len(set(slice_words)) == len(slice_words)),
        ("slice's words fit", max(slice_words) < R["TS_WORDS"]),
    ]
    asserted("record.h: words and numbers read back", conditions, started)


def reach(pieces, members, tile, across, first_row, end_row):
    """The members of a tile whose box rows reach its rows [first_row, end_row)."""
    top = TILE * (tile // across)
    box = pieces["box"][members].astype(np.int64)
    first = np.maximum(box[:, 2], top) - top
    last = np.minimum(box[:, 3], top + TILE - 1) - top
    return members[(first < end_row) & (last >= first_row)]


def item_lists(laid):
    """{(layer, item): sorted pieces of its list}, from the records' slots and
    entries and the slices' places."""
    out = {}
    count = laid["slice_records"]
    words, records = laid["slice_words"], laid["records"]
    item_of = {tuple(item): n for n, item in enumerate(laid["items"][:, :3].tolist())}
    for s in range(len(words)):
        for place in range(int(words[s, R["TS_RECORDS"]])):
            row = records[s * count + place]
            w = int(row[0])
            key = (M["TR_TILE"](w), M["TR_FIRST_ROW"](w), M["TR_END_ROW"](w))
            for layer in range(len(laid["layers"])):
                first = int(words[s, M["TS_PLACE"](layer)])
                first += int(row[M["TR_LAYER_SLOT"](layer)])
                entries = int(row[M["TR_LAYER_ENTRIES"](layer)])
                pieces = laid["lists"][layer]["pieces"][first : first + entries]
                out[(layer, item_of[key])] = np.sort(pieces)
    return out


def binning_case(name, laid):
    """Every item's list (a whole tile: its members; a band: those reaching its rows)
    equal as a multiset to `bin_triangles`' list; every slot written once; each list's
    slots in the slot words of the record, its pieces' packed records in the slots."""
    started = time.perf_counter()
    across, down = laid["grid"]
    lists = item_lists(laid)
    wrong, unwritten, packed, covered = 0, 0, 0, True
    for layer, pieces in enumerate(laid["pieces"]):
        _, offsets, members = bin_triangles(pieces, across, down)
        written = laid["lists"][layer]["pieces"]
        unwritten += int((written < 0).sum())
        sizes = []
        for n, (tile, first_row, end_row) in enumerate(laid["items"][:, :3].tolist()):
            own = members[offsets[tile] : offsets[tile + 1]].astype(np.int64)
            want = np.sort(reach(pieces, own, tile, across, first_row, end_row))
            got = lists.get((layer, n), np.zeros(0, dtype=np.int64))
            wrong += not np.array_equal(got, want)
            sizes.append(len(got))
        covered &= sum(sizes) == len(written)
        slots = laid["lists"][layer]["slots"]
        index = pack_records(pieces)[np.maximum(written, 0)]
        packed += int((slots != index).any(axis=1).sum())
    conditions = [
        (f"{wrong} lists differ from the binning", wrong == 0),
        (f"{unwritten} slots unwritten", unwritten == 0),
        ("the records' lists cover every slot", covered),
        (f"{packed} slots not their piece's record", packed == 0),
        ("every item a record", len(lists) == len(laid["items"]) * len(laid["pieces"])),
    ]
    asserted(f"{name}: lists against the binning", conditions, started)


def random_log_case(name, scene, view, laid, heavy):
    """A random log over CORES cores: the same items, records and slices' words, and
    every item's list the same multiset, as with one core."""
    started = time.perf_counter()
    rng = np.random.default_rng(SEED)
    total = int(laid["ranges"]["count"].sum())
    log = rng.integers(0, CORES, total)
    other = threads.layout(scene, view, log, heavy=heavy, cores=CORES)
    mine, theirs = item_lists(laid), item_lists(other)
    same = sum(np.array_equal(mine[key], theirs.get(key)) for key in mine)
    used = len(np.unique(log))
    conditions = [
        ("the same items", np.array_equal(laid["items"], other["items"])),
        ("the same records", np.array_equal(laid["records"], other["records"])),
        (
            "the same slices' words",
            np.array_equal(laid["slice_words"], other["slice_words"]),
        ),
        (f"{len(mine) - same} lists differ", same == len(mine) == len(theirs)),
        (f"{used} cores counted", used > 1 or total < 2),
        ("positions of every core", other["positions"].shape[1] == CORES),
    ]
    asserted(f"{name}: a random log of {CORES} cores", conditions, started)


def bands_case(name, laid, heavy, full):
    """Each tile's items cover its rows 0 to 32 once, in even bounds; a cut tile past
    `heavy`, in at most min(kBandsMost, ceil(weight / heavy)) bands; a slice's items
    within its records, and (`full`) some slice filled to them by its bands."""
    started = time.perf_counter()
    items = laid["items"]
    weight = sum(layer.sum(0) for layer in laid["counts"])
    holes, odd, wrong_cut = 0, 0, 0
    for tile in range(len(weight)):
        own = items[items[:, 0] == tile]
        bounds = np.concatenate([own[:, 1], own[-1:, 2]])
        holes += not (
            bounds[0] == 0
            and bounds[-1] == 2 * GROUPS
            and np.array_equal(own[1:, 1], own[:-1, 2])
            and (np.diff(bounds) > 0).all()
        )
        odd += int((bounds % 2).any())
        if len(own) > 1:
            most = min(G["kBandsMost"], -(-int(weight[tile]) // heavy))
            wrong_cut += weight[tile] <= heavy or len(own) > most
            wrong_cut += not np.array_equal(own[:, 3], own[0, 3] + np.arange(len(own)))
        else:
            wrong_cut += own[0, 3] != -1
    per_slice = np.bincount(laid["slices"]["of"][items[:, 0]])
    filled = int((per_slice == laid["slice_records"]).sum())
    banded = int((laid["item_count"] > 1).sum())
    conditions = [
        (f"{holes} tiles' rows not covered once", holes == 0),
        (f"{odd} tiles with an odd bound", odd == 0),
        (f"{wrong_cut} tiles cut against the rule", wrong_cut == 0),
        (f"{banded} tiles in bands", banded > 0),
        ("slices within their records", per_slice.max() <= laid["slice_records"]),
        (f"{filled} slices filled", filled > 0 or not full),
    ]
    asserted(f"{name}: bands of the tiles past {heavy}", conditions, started)


def places_case(name, laid, view):
    """Each layer's slice places the running sum of the slices' entries; a slice's
    records in record order (weight, tile, first row), its words their sums, its
    lists in record order from its place, word 3 its tile's page in `view`'s target."""
    started = time.perf_counter()
    words, records = laid["slice_words"].astype(np.int64), laid["records"]
    count = laid["slice_records"]
    across = laid["grid"][0]
    first = (view or {}).get("page_first", 0)
    each_row = (view or {}).get("page_across", across)
    sums, order, slots, pages = True, True, True, True
    for layer in range(len(laid["layers"])):
        sizes = words[:, M["TS_ENTRIES"](layer)]
        sums &= np.array_equal(words[:, M["TS_PLACE"](layer)], np.cumsum(sizes) - sizes)
    for s in range(len(words)):
        own = records[s * count : s * count + int(words[s, R["TS_RECORDS"]])]
        weight = own[:, 1].astype(np.int64)
        key = [
            (-int(r[1]), M["TR_TILE"](int(r[0])), M["TR_FIRST_ROW"](int(r[0])))
            for r in own
        ]
        order &= all(a < b for a, b in itertools.pairwise(key))
        order &= int(weight.sum()) == words[s, R["TS_WEIGHT"]]
        tiles = np.array([M["TR_TILE"](int(r[0])) for r in own])
        page = first + tiles // across * each_row + tiles % across
        pages &= np.array_equal(own[:, 3].astype(np.int64), page)
        order &= not records[s * count + len(own) : (s + 1) * count].any()
        for layer in range(len(laid["layers"])):
            slot = own[:, M["TR_LAYER_SLOT"](layer)].astype(np.int64)
            entries = own[:, M["TR_LAYER_ENTRIES"](layer)].astype(np.int64)
            slots &= np.array_equal(slot, np.cumsum(entries) - entries)
            slots &= int(entries.sum()) == words[s, M["TS_ENTRIES"](layer)]
    conditions = [
        ("places the running sum", sums),
        ("records in record order, the words their sums", order),
        ("lists in record order from the slice's place", slots),
        ("slices of the grid", len(words) == len(laid["slices"]["tiles"])),
        ("word 3 the tile's page", pages),
    ]
    asserted(f"{name}: slices' places and records", conditions, started)


def positions_case(name, laid):
    """Each core's first position in an item its record's slot plus the entries of the
    cores before it; each positions page read back (frame.h TF_L_POSITIONS) to them,
    a cut tile's word to its bands' entries, every other word 0."""
    started = time.perf_counter()
    items, sliced = laid["items"], laid["slices"]
    count, most, pair = laid["slice_records"], G["kSliceTilesMost"], G["kBandWords"]
    tile_words = most * (laid["held"] or len(sliced["tiles"]))
    slot_of = {}
    for s in range(len(sliced["tiles"])):
        for place in range(int(laid["slice_words"][s, R["TS_RECORDS"]])):
            row = laid["records"][s * count + place]
            w = int(row[0])
            key = (M["TR_TILE"](w), M["TR_FIRST_ROW"](w), M["TR_END_ROW"](w))
            slot_of[key] = row
    sums, read, spare = True, True, True
    for layer, page in enumerate(laid["positions_pages"]):
        positions = laid["positions"][layer]
        per = laid["item_entries"][:, layer, :]
        slots = np.array(
            [
                int(slot_of[tuple(i)][M["TR_LAYER_SLOT"](layer)])
                for i in items[:, :3].tolist()
            ]
        )
        want = slots[None, :] + (np.cumsum(per, axis=1) - per).T
        sums &= np.array_equal(positions, want)
        used = np.zeros(page.shape[1], dtype=bool)
        for s, run in enumerate(sliced["tiles"]):
            for column, tile in enumerate(run):
                word = page[:, s * most + column].astype(np.int64)
                used[s * most + column] = True
                own = np.flatnonzero(items[:, 0] == tile)
                if not word[0] & G["kPosCut"]:
                    read &= len(own) == 1 and np.array_equal(word, positions[:, own[0]])
                    continue
                bands = int(word[0] >> G["kPosBandsShift"]) & G["kPosBandsMask"]
                entry = word & G["kPosEntryMask"]
                read &= bands == len(own) and bool((entry == entry[0]).all())
                for band, item in enumerate(own):
                    at = tile_words + pair * (int(entry[0]) + band)
                    used[at : at + pair] = True
                    rows = items[item, 1] | items[item, 2] << G["kBandRowsEndShift"]
                    read &= bool((page[:, at] == rows).all())
                    read &= np.array_equal(page[:, at + 1], positions[:, item])
        spare &= not page[:, ~used].any()
    conditions = [
        ("positions: the slot and the cores before", sums),
        ("pages read back to the positions", read),
        ("unused words 0", spare),
    ]
    asserted(f"{name}: each core's positions pages", conditions, started)
