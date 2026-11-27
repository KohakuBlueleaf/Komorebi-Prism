"""The preset `gi_threads`: `lit_threads` lit with the indirect field; the field's
update the job thread's job on clusters 2 and 3, a graph the dispatcher keeps (its
applies the transport's on every core, each a core step of the frame's thread), the
field's version switched between two frames; its picture `gi`'s."""

import runpy
from pathlib import Path

from prism.core.pipeline import Pipeline
from prism.program.threads import implementations  # noqa: F401  (registers them)
from prism.stages.indirect import near_tile  # noqa: F401  (registers it)

STAGE_WISE = runpy.run_path(str(Path(__file__).with_name("gi.py")))

PIPELINE = Pipeline(
    "gi_threads",
    [
        "raster.threads",
        "material.texture.threads",
        "direct.shadow_pcf",
        "indirect.transport.threads",
        "indirect.field_update.threads",
        "indirect.near_tile",
        "direct.light.threads_field",
        "post.show.threads",
    ],
    inputs=STAGE_WISE["PIPELINE"].inputs,
)
OPTIONS = STAGE_WISE["OPTIONS"] | {
    "tile_thread": "prism.program.threads.tiles:GI",
    "push": False,
    "update_beside": True,
    "near_tile": False,
}
SCENE_INPUTS = STAGE_WISE["SCENE_INPUTS"]
SCENE_FILES = STAGE_WISE["SCENE_FILES"]
REFERENCE = STAGE_WISE["REFERENCE"]
JUDGE = STAGE_WISE["JUDGE"]
# without the scene's far field: the light unit that reads no field version
FAR_FIELD_ABSENT = {"direct.light.threads_field": "direct.light.threads"}
