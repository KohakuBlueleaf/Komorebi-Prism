"""The preset `lit_tile`: `lit`'s implementations and frames, LIGHT's last command of a
colour view converting its colour planes for display on each tile's owner (the option
light_shows), so no SHOW command is sent; the pictures are `lit`'s."""

import runpy
from pathlib import Path

from prism.core.pipeline import Pipeline

STAGE_WISE = runpy.run_path(str(Path(__file__).with_name("lit.py")))  # the preset `lit`

PIPELINE = Pipeline(
    "lit_tile", STAGE_WISE["PIPELINE"].names(), inputs=STAGE_WISE["PIPELINE"].inputs
)
OPTIONS = STAGE_WISE["OPTIONS"] | {"light_shows": True}
SCENE_INPUTS = STAGE_WISE["SCENE_INPUTS"]
REFERENCE = STAGE_WISE["REFERENCE"]
JUDGE = STAGE_WISE["JUDGE"]
