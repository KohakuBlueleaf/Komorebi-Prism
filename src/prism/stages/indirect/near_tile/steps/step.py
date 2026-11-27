"""The one-tile product as a step of the tile thread: the tile's E at half rows into the
plane near.light (marked on when it is the frame's), before the light step."""

from pathlib import Path

from prism.core.headers import constexpr
from prism.core.thread.module import Plane, Step

KERNELS = Path(__file__).resolve().parent / "kernels"
NS = constexpr(KERNELS / "near_tile_step.h")
STAGE = "stages/indirect/near_tile"

NEAR_LIGHT = Plane("near.light", "fp32", tiles=NS["kNearPlaneBytes"] // 4096)

NEAR_TILE = Step(
    name="near_tile",
    header=f"{STAGE}/steps/kernels/near_tile_step.hpp",
    requests=("light",),
    leaves=(NEAR_LIGHT.name,),
    words=("light", "upsample", "on"),
    thread=f"{STAGE}/thread/near_tile_frame_words.c",
)
