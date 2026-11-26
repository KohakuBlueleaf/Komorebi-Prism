"""The preset `gi_tile`: `gi`'s implementations and frames, LIGHT's last command of a
colour view converting its colour planes for display on each tile's owner (the option
light_shows), so no SHOW command is sent; the field's update on the cluster beside the
frames' while frames go on with the old field, the new one swapped in between two frames
(the option update_beside); the pictures are `gi`'s."""

import runpy
from pathlib import Path

from prism.core.pipeline import Pipeline

STAGE_WISE = runpy.run_path(str(Path(__file__).with_name("gi.py")))  # the preset `gi`

PIPELINE = Pipeline(
    "gi_tile", STAGE_WISE["PIPELINE"].names(), inputs=STAGE_WISE["PIPELINE"].inputs
)
OPTIONS = STAGE_WISE["OPTIONS"] | {"light_shows": True, "update_beside": True}
SCENE_INPUTS = STAGE_WISE["SCENE_INPUTS"]
REFERENCE = STAGE_WISE["REFERENCE"]
JUDGE = STAGE_WISE["JUDGE"]
