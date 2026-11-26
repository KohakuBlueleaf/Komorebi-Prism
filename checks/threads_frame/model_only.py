"""The parts of the threads' checks that need no card, against the model itself: the
layers read back from the mesh blocks, the card's records, the tensors' images, the
log's reading, the comparisons on a copy and on a changed copy, the code tables."""

import time

import numpy as np

from checks.raster_model.compare import asserted
from prism.check.threads import codes, compare
from prism.check.threads.layers import card_records, flat_scene, frame_layers
from prism.check.threads.model import (
    PORTS_CORES,
    counts_image,
    laid_out,
    log_cores,
    pages,
    positions_image,
    records_image,
    rows_image,
    slices_image,
    view_of,
    words_of,
)
from prism.program.dispatch.thread import Capacity
from prism.stages.raster.model import threads
from prism.stages.raster.model.numbers import GROUPS, K, S
from prism.stages.raster.model.records import mesh_blocks, pack_records
from prism.stages.raster.threads.layout import slices_of
from prism_reference.raster.fill import tile_counts
from prism_reference.raster.setup import boxes, grid, setup
from prism_reference.scene.frame import TILE

HEAVY_PERCENTILE = 95  # of the tiles with entries: the weight past which a tile is cut
RANGES_MOST = 1 << 16  # the model capacity's ranges
SEED = 5
PAGE_BYTES = 2048  # a list page of the model's images
WEIGHTED = [K["kRecCol"] + n for n in range(9)] + [S["kRecShadeWord"]]


def capacity_of(scene):
    """A capacity holding the scene's frame: its slices by the geometry's layout."""
    across, down = grid(scene)
    return Capacity(RANGES_MOST, slices_of(across, down))


def heavy_of(layers):
    """The HEAVY_PERCENTILE-th weight of the tiles with entries over the layers."""
    weight = sum(tile_counts(boxes(one), *grid(one)) for _, one, _ in layers)
    return max(1, int(np.percentile(weight[weight > 0], HEAVY_PERCENTILE)))


def layers_case(name, scene, layers):
    """The flat scene's blocks equal the blocks it was read from; an unshaded layer's
    records equal the model's of the scene; a shaded layer's equal setup's records
    but for the colour planes and the shade word, its material bits the shade row's."""
    started = time.perf_counter()
    round_trip, unshaded, kept, material = True, True, True, True
    for _, one, shade in layers:
        blocks = mesh_blocks(one)
        round_trip &= np.array_equal(
            mesh_blocks(flat_scene(blocks, len(one["indices"]), one)), blocks
        )
        pieces, packed = card_records(one, shade)
        plain = pack_records(setup(one))
        if shade is None:
            unshaded &= np.array_equal(packed, plain)
            continue
        other = np.setdiff1d(np.arange(packed.shape[1]), WEIGHTED)
        kept &= np.array_equal(packed[:, other], plain[:, other])
        word = packed[:, S["kRecShadeWord"]].astype(np.int64)
        row = shade[1, pieces["tri"]].astype(np.int64)
        material &= np.array_equal(word & 0xFFFF, row & 0xFFFF)
    if all(shade is None for _, _, shade in layers):
        unshaded &= np.array_equal(
            pack_records(setup(layers[0][1])), pack_records(setup(scene))
        )
    conditions = [
        ("blocks read back", round_trip),
        ("unshaded records the model's", unshaded),
        ("shaded records but planes and shade word", kept),
        ("shade word's material", material),
        ("layers given", len(layers) > 0),
    ]
    asserted(f"{name}: layers as the card holds them", conditions, started)


def images_case(name, laid, held):
    """Each tensor's image through pages and back: the records, slices, counts, row
    histograms (starts, ends) and positions; the lists' slots."""
    started = time.perf_counter()
    records = records_image(laid, held)
    back = words_of(pages(records, 64)).reshape(records.shape)
    tiles = laid["counts"][0].shape[1]
    rows = rows_image(laid, 0, GROUPS * tiles)
    halves = rows.view(np.uint16).reshape(len(rows), -1)
    halves = halves[:, : tiles * 2 * GROUPS].reshape(len(rows), tiles, 2, GROUPS)
    slots = laid["lists"][0]["slots"]
    flat = words_of(pages(slots, PAGE_BYTES)).reshape(-1)
    positions = positions_image(laid, 0, laid["positions_pages"][0].shape[1])
    words = slices_image(laid, held)[: len(laid["places"])]
    at = threads.M["TS_PLACE"](0)
    places = words[:, at : at + laid["places"].shape[1]].astype(np.int64)
    conditions = [
        ("records", np.array_equal(back, records)),
        ("slices' places", np.array_equal(places, laid["places"])),
        (
            "counts",
            np.array_equal(counts_image(laid, 0, tiles), laid["counts"][0]),
        ),
        ("row starts", np.array_equal(halves[:, :, 0], laid["starts"][0])),
        ("row ends", np.array_equal(halves[:, :, 1], laid["ends"][0])),
        ("lists", np.array_equal(flat[: slots.size].reshape(slots.shape), slots)),
        ("positions", np.array_equal(positions, laid["positions_pages"][0])),
    ]
    asserted(f"{name}: tensors' images", conditions, started)


def log_case():
    """A log written as Komorebi's pull writes it, read back to each range's core."""
    started = time.perf_counter()
    rng = np.random.default_rng(SEED)
    ranges, held = 300, 320
    core_of = rng.integers(0, 40, ranges)
    words = np.zeros(PORTS_CORES * (1 + held), np.uint32)
    for core in range(PORTS_CORES):
        own = np.flatnonzero(core_of == core)
        words[core] = len(own)
        at = PORTS_CORES + core * held
        words[at : at + len(own)] = own
    got, ranks = log_cores(words.tobytes(), ranges)
    twice = words.copy()
    twice[PORTS_CORES + held * int(core_of[0])] = 1  # range 1 named twice
    try:
        log_cores(twice.tobytes(), ranges)
        refused = core_of[0] == core_of[1]
    except ValueError:
        refused = True
    conditions = [
        ("cores read back", np.array_equal(got, core_of)),
        ("ranks", ranks == sorted(set(core_of.tolist()))),
        ("a range twice refused", refused),
    ]
    asserted("the count pull's log", conditions, started)


def comparisons_case(name, laid, held):
    """The comparisons on the model against itself (equal), with two entries of an
    item swapped (equal, reordered), an entry changed (the item and its record named),
    a record's word changed, a picture's pixel changed (its tile first)."""
    started = time.perf_counter()
    slots = laid["lists"][0]["slots"]
    spans = [s for s in compare.item_spans(laid, 0) if s[5] > 1]
    swapped, changed = slots.copy(), slots.copy()
    number, _, _, _, slot, _ = spans[0]
    swapped[[slot, slot + 1]] = swapped[[slot + 1, slot]]
    changed[slot, K["kRecIndex"]] += 1 << 20
    records = records_image(laid, held)
    wrong = records.copy()
    wrong[number, 3] += 1
    picture = np.zeros((3 * TILE, 5 * TILE, 4), np.uint8)
    other = picture.copy()
    other[TILE + 3, 2 * TILE + 7, 1] = 9
    same = compare.lists(laid, 0, slots)
    reordered = compare.lists(laid, 0, swapped)
    differ = compare.lists(laid, 0, changed)
    record = compare.records(wrong, records, held.slice_records)
    shown = compare.pictures(other, picture)
    conditions = [
        ("the lists equal themselves", same["equal"] and not same["items_reordered"]),
        ("a swap reordered", reordered["equal"] and reordered["items_reordered"] == 1),
        ("a change found", not differ["equal"] and differ["first"]["record"] == number),
        ("its record named", record["first_record"]["number"] == number),
        ("the first tile", shown["first_tile"]["tile"] == 5 + 2),
        ("its rows", shown["first_tile"]["rows"] == [3, 4]),
        ("a picture equals itself", compare.pictures(picture, picture)["equal"]),
    ]
    asserted(f"{name}: comparisons", conditions, started)


def codes_case():
    """Every give-up place of the loop and the geometry named, the view's codes and
    the thread's marks named."""
    started = time.perf_counter()
    wheres = codes.where_names()
    conditions = [
        ("the loop's 16 places", all(n in wheres for n in range(112, 128))),
        ("the geometry's places", any("kWhereSumRead" in v for v in wheres.values())),
        ("the view's codes", codes.result_name(16 + 75) == "DP_LATE_TILE"),
        ("the thread's marks", len(codes.progress_names()) == 4),
        ("Komorebi's names kept", codes.where_name("next") == "next"),
    ]
    asserted("code tables", conditions, started)


def run(name, scene, options, order=None):
    """Every model-only case on `scene` (a view at its size) with the preset's options;
    a random log of several cores laid out too."""
    layers = frame_layers(scene, options.get("materials"), options.get("lights"), order)
    layers_case(name, scene, layers)
    held = capacity_of(scene)
    heavy = heavy_of(layers)
    laid = laid_out(layers, view_of(scene), held, heavy, threads.RANGE_BLOCKS)
    images_case(name, laid, held)
    comparisons_case(name, laid, held)
    total = int(laid["ranges"]["count"].sum())
    log = np.random.default_rng(SEED).integers(0, 12, total)
    many = laid_out(layers, view_of(scene), held, heavy, threads.RANGE_BLOCKS, log, 12)
    images_case(f"{name}, 12 cores", many, held)
    started = time.perf_counter()
    asserted(
        f"{name}: one core and 12 the same records",
        [("records", np.array_equal(many["records"], laid["records"]))],
        started,
    )
