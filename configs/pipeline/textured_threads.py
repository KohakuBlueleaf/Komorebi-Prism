"""The preset `textured_threads`: `textured` as threads; each view the dispatcher's pulls
(count, the sums, place, then the tile threads: visibility, material, post), its
picture `textured`'s."""

import runpy
from pathlib import Path

from prism.core.pipeline import Pipeline
from prism.program.threads import implementations  # noqa: F401  (registers them)

STAGE_WISE = runpy.run_path(str(Path(__file__).with_name("textured.py")))

PIPELINE = Pipeline(
    "textured_threads",
    ["raster.threads", "material.texture.threads", "post.show.threads"],
    inputs=STAGE_WISE["PIPELINE"].inputs,
)
OPTIONS = STAGE_WISE["OPTIONS"] | {
    "tile_thread": "prism.program.threads.tiles:TEXTURED",
    "push": False,
}
SCENE_INPUTS = STAGE_WISE["SCENE_INPUTS"]
REFERENCE = STAGE_WISE["REFERENCE"]
JUDGE = STAGE_WISE["JUDGE"]
