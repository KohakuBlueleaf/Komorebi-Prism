"""The one-tile product as a step of the tile thread: E = W_T . S_T of the tile on the
matrix engine into the plane near.light (marked on when it is the frame's), with the
upsample's weights, before the light step."""

from pathlib import Path

import komorebi as km

from prism.core.headers import constexpr
from prism.core.thread.module import Plane, Step

KERNELS = Path(__file__).resolve().parent / "kernels"
NS = constexpr(KERNELS / "near_tile_step.h")
STAGE = "stages/indirect/near_tile"

NEAR_LIGHT = Plane("near.light", "fp32", tiles=NS["kNearPlaneBytes"] // 4096)

NEAR_TILE = Step(
    name="near_tile",
    header=f"{STAGE}/steps/kernels/near_tile_step.hpp",
    requests=("weights", "operand", "upsample"),
    leaves=(NEAR_LIGHT.name,),
    buffers={
        "w": (NS["kNearPartTiles"], NS["kNearWTileBytes"], "pack", km.bfp8_b),
        "s": (1, NS["kNearSTileBytes"], "pack", km.bf16),
        "e": (1, NS["kNearETileBytes"], "pack", km.fp32),
    },
    words=("weights", "operand", "upsample", "half", "on"),
    thread=f"{STAGE}/thread/near_tile_frame_words.c",
)
