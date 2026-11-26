"""The cases of the tile threads' model: record.h's words, every list against the
reference's binning, a random log's lists and records, the bands, the slices' places."""

import time

import numpy as np

from checks.raster_model.compare import asserted
from prism.stages.raster.model import threads
from prism.stages.raster.model.numbers import GROUPS
from prism.stages.raster.model.records import pack_records
from prism.stages.raster.model.threads import RECORD_H, TR_LAYERS, M, R, macros
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
    item_of = {tuple(item): n for n, item in enumerate(laid["items"].tolist())}
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
        for n, (tile, first_row, end_row) in enumerate(laid["items"].tolist()):
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


def random_log_case(name, scene, view, laid, slice_tiles, heavy):
    """A random log over CORES cores: the same items, records and slices' words, and
    every item's list the same multiset, as with one core."""
    started = time.perf_counter()
    rng = np.random.default_rng(SEED)
    total = int(laid["ranges"]["count"].sum())
    log = rng.integers(0, CORES, total)
    other = threads.layout(scene, view, log, slice_tiles, heavy, cores=CORES)
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


def bands_case(name, laid, heavy):
    """Each tile's items cover its rows 0 to 32 once, in even bounds; a tile is cut
    exactly when its entries pass `heavy`; every banded tile counted."""
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
        cut = len(own) > 1 or tuple(own[0, 1:]) != (0, 2 * GROUPS)
        wrong_cut += cut and weight[tile] <= heavy
    banded = int((laid["item_count"] > 1).sum())
    conditions = [
        (f"{holes} tiles' rows not covered once", holes == 0),
        (f"{odd} tiles with an odd bound", odd == 0),
        (f"{wrong_cut} tiles cut at or under the weight", wrong_cut == 0),
        (f"{banded} tiles in bands", banded > 0),
    ]
    asserted(f"{name}: bands of the tiles past {heavy}", conditions, started)


def places_case(name, laid):
    """Each layer's slice places the running sum of the slices' entries; a slice's
    records in order of weight, its words their sums, its slots from 0 in order."""
    started = time.perf_counter()
    words, records = laid["slice_words"].astype(np.int64), laid["records"]
    count = laid["slice_records"]
    sums, order, slots = True, True, True
    for layer in range(len(laid["layers"])):
        sizes = words[:, M["TS_ENTRIES"](layer)]
        sums &= np.array_equal(words[:, M["TS_PLACE"](layer)], np.cumsum(sizes) - sizes)
    for s in range(len(words)):
        own = records[s * count : s * count + int(words[s, R["TS_RECORDS"]])]
        weight = own[:, 1].astype(np.int64)
        order &= bool((np.diff(weight) <= 0).all())
        order &= int(weight.sum()) == words[s, R["TS_WEIGHT"]]
        order &= not records[s * count + len(own) : (s + 1) * count].any()
        for layer in range(len(laid["layers"])):
            first = own[:, M["TR_LAYER_SLOT"](layer)].astype(np.int64)
            entries = own[:, M["TR_LAYER_ENTRIES"](layer)].astype(np.int64)
            by_slot = np.lexsort((entries, first))
            ends = np.cumsum(entries[by_slot])
            slots &= np.array_equal(first[by_slot], ends - entries[by_slot])
            slots &= int(entries.sum()) == words[s, M["TS_ENTRIES"](layer)]
    conditions = [
        ("places the running sum", sums),
        ("records in order of weight, the words their sums", order),
        ("slots from the slice's place, in order, each once", slots),
        ("slices of the grid", len(words) == len(laid["slices"]["tiles"])),
    ]
    asserted(f"{name}: slices' places and records", conditions, started)
