"""The preset `gi_tile`: `gi`'s implementations and frames, LIGHT's last command of a
colour view converting its colour planes for display on each tile's owner (the option
light_shows), so no SHOW command is sent; the pictures are `gi`'s."""

import runpy
from pathlib import Path

from prism.core.pipeline import Pipeline

STAGE_WISE = runpy.run_path(str(Path(__file__).with_name("gi.py")))  # the preset `gi`

PIPELINE = Pipeline(
    "gi_tile", STAGE_WISE["PIPELINE"].names(), inputs=STAGE_WISE["PIPELINE"].inputs
)
OPTIONS = STAGE_WISE["OPTIONS"] | {"light_shows": True}
SCENE_INPUTS = STAGE_WISE["SCENE_INPUTS"]
REFERENCE = STAGE_WISE["REFERENCE"]
JUDGE = STAGE_WISE["JUDGE"]
