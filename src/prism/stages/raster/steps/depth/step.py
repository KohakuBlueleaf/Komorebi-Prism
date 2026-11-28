"""The DEPTH view's last step of the tile thread: the visibility's 1/z pushed as an
output block, turned row-major on the data-movement CPU that takes it and written to the
tile's page of the view's target, with its levels when the view has them; with T the
tile's T block beside it."""

from dataclasses import replace
from pathlib import Path

from prism.core.headers import constexpr
from prism.core.thread.module import Output, Step

POST_KERNELS = (
    Path(__file__).resolve().parents[3] / "post" / "show" / "steps" / "kernels"
)
PS = constexpr(POST_KERNELS / "post_step.h")
STAGE = "stages/raster"

DEPTH_OUT = Step(
    name="depth_out",
    header=f"{STAGE}/steps/depth/kernels/depth_out.hpp",
    outputs=(Output("depth", PS["kDepthBlockBytes"], 2, convert="depth_out_convert"),),
    reads=("frame.visibility",),
    keeps={"scratch": PS["kPostScratchBytes"]},
    words=("pages", "levels", "levels_shift", "tops"),
    thread=f"{STAGE}/thread/depth_out_frame_words.c",
    colour=False,
    depth=True,
)

# with the sun map's T (the option shadow_transmit): the tile's T block beside it
DEPTH_OUT_TRANSMIT = replace(
    DEPTH_OUT,
    words=(*DEPTH_OUT.words, "transmit", "transmit_base", "transmit_channels"),
)
