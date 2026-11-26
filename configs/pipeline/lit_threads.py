"""The preset `lit_threads`: `lit` as threads; the sun's views (its command, after a
move) and the eye's view each the dispatcher's pulls, the tile threads visibility, the
lit material, light and post (a DEPTH view: visibility, the lit material, depth out),
its picture `lit`'s."""

import runpy
from pathlib import Path

from prism.core.pipeline import Pipeline
from prism.program.threads import implementations  # noqa: F401  (registers them)

STAGE_WISE = runpy.run_path(str(Path(__file__).with_name("lit.py")))

PIPELINE = Pipeline(
    "lit_threads",
    [
        "raster.threads",
        "material.texture.threads",
        "direct.shadow_pcf",
        "direct.light.threads",
        "post.show.threads",
    ],
    inputs=STAGE_WISE["PIPELINE"].inputs,
)
OPTIONS = STAGE_WISE["OPTIONS"] | {
    "tile_thread": "prism.program.threads.tiles:LIT",
    "push": False,
}
SCENE_INPUTS = STAGE_WISE["SCENE_INPUTS"]
REFERENCE = STAGE_WISE["REFERENCE"]
JUDGE = STAGE_WISE["JUDGE"]
