"""The cases of the model alone: each scene's counters and histograms, the frame's pages
decoded back to the reference's frame, and SETUP at the middle pass's slots writing the
lists `build_lists` makes."""

import time

import numpy as np

from checks.raster_model.compare import asserted, compare
from prism.stages.raster.model import count, frame, lists, middle, numbers, records
from prism_reference.raster.fill import bin_triangles
from prism_reference.raster.frames import rasterize
from prism_reference.raster.setup import setup

CORES = 120
FILLS = (5, CORES, 240)


def scene_counts(scene):
    """The scene's counters and histograms over CORES counting cores: (counts, rows,
    starts, ends)."""
    recs = setup(scene)
    triangles = len(scene["indices"])
    counts, rows = count.counters(recs, triangles, CORES)
    starts, ends = count.histograms(recs, triangles, CORES)
    return counts, rows, starts, ends


def frame_case(name, scene):
    """decode_frame of frame_of of the reference's plain frame is that frame."""
    started = time.perf_counter()
    plain = rasterize(scene)
    images = {key: plain[key] for key in ("colour", "depth", "tri")}
    decoded = frame.decode_frame(frame.frame_of(images))
    seconds = time.perf_counter() - started
    compare(f"{name}: decode_frame of frame_of is the frame", decoded, images, seconds)


def setup_writes_lists_case(scene):
    """SETUP at the middle pass's next slots (7 counting cores, 5 fill cores) writes the
    lists `build_lists` makes; the counters sum to the binning."""
    started = time.perf_counter()
    recs = setup(scene)
    _, offsets, members = bin_triangles(recs)
    plain = records.pack_records(recs)
    triangles, cores = len(scene["indices"]), 7
    counts, rows = count.counters(recs, triangles, cores)
    mid = middle.middle(counts, rows, 5)
    want, directory = lists.build_lists(plain, offsets, members, mid["tiles_of"])
    written = mid["pages"].reshape(-1, numbers.SLOT).copy()
    next_slot = mid["next"].astype(np.int64)
    table = count.entries(recs, triangles, cores)
    for record, core, tile in zip(table["record"], table["core"], table["tile"]):
        written[next_slot[core, tile]] = plain[record]
        next_slot[core, tile] += 1
    conditions = [
        ("lists", np.array_equal(written.reshape(want.shape), want)),
        ("directory", np.array_equal(directory, mid["directory"])),
        ("counters", np.array_equal(counts.sum(0), np.diff(offsets))),
    ]
    asserted("tiny: SETUP at the middle's slots: build_lists'", conditions, started)
