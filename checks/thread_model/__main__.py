"""Runs every case on `tiny`, `s10k` (its triangles in three layers) and Sponza's
overview at 1,920 x 1,080; exit 1 on a difference."""

import json
import sys
import time

import numpy as np

from checks.raster_model.compare import RESULTS
from checks.thread_model import cases
from prism.stages.raster.model.threads import layout
from prism_common.paths import data_root
from prism_reference.raster.fill import tile_counts
from prism_reference.raster.setup import boxes, grid
from prism_reference.scene.generated import make_preset
from prism_reference.scene.public.views import make_view

SLICE_TILES = 8
HEAVY_PERCENTILE = 95  # of the tiles with entries: the weight past which a tile is cut


def in_layers(scene, layers):
    """(name, scene) of `layers` layers: triangle t in layer t mod `layers`."""
    count = len(scene["indices"])
    return [
        (
            f"layer {n}",
            {**scene, "indices": scene["indices"][np.arange(n, count, layers)]},
        )
        for n in range(layers)
    ]


def heavy_of(scene):
    """The HEAVY_PERCENTILE-th weight of the tiles with entries, from the reference's
    counts over every layer."""
    named = [("scene", scene)] if isinstance(scene, dict) else scene
    weight = sum(tile_counts(boxes(one), *grid(one)) for _, one in named)
    return max(1, int(np.percentile(weight[weight > 0], HEAVY_PERCENTILE)))


def main():
    """Runs every case; exit 1 when one differs."""
    started = time.perf_counter()
    sponza = make_view("sponza_overview", data_root())
    scenes = [
        ("tiny", make_preset("tiny"), None),
        ("s10k in 3 layers", in_layers(make_preset("s10k"), 3), None),
        ("sponza 1920x1080", sponza, {"size": (1920, 1080)}),
    ]
    cases.words_case()
    for name, scene, view in scenes:
        sized = scene if view is None else {**scene, **view}
        heavy = heavy_of(sized)
        laid = layout(scene, view, None, SLICE_TILES, heavy)
        cases.binning_case(name, laid)
        cases.bands_case(name, laid, heavy)
        cases.places_case(name, laid)
        cases.random_log_case(name, scene, view, laid, SLICE_TILES, heavy)
    different = [r["case"] for r in RESULTS if not r["equal"]]
    seconds = round(time.perf_counter() - started, 1)
    print(
        json.dumps({"cases": len(RESULTS), "different": different, "seconds": seconds})
    )
    return 1 if different else 0


if __name__ == "__main__":
    sys.exit(main())
