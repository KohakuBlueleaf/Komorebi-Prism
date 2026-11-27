"""The display conversion as a step of the tile thread: the visibility's colour planes
(through the file's view transform when one is on: its cube pages asked into kept
slots) pushed as an output block, converted by SHOW's rule on the data-movement CPU
that takes it and written to the tile's display page."""

from pathlib import Path

from prism.core.headers import constexpr
from prism.core.thread.module import Output, Step

KERNELS = Path(__file__).resolve().parent / "kernels"
PS = constexpr(KERNELS / "post_step.h")
VIEW = constexpr(KERNELS.parent.parent / "kernels" / "view.h")
STAGE = "stages/post/show"

POST = Step(
    name="post",
    header=f"{STAGE}/steps/kernels/post_step.hpp",
    outputs=(Output("display", PS["kPostBlockBytes"], 2, convert="post_convert"),),
    reads=("frame.visibility",),
    requests=("view",),
    keeps={
        "table": PS["kPostTableBytes"],
        "scratch": PS["kPostScratchBytes"],
        "view": VIEW["kViewRegionBytes"],
        "slots": VIEW["kViewSlots"] * VIEW["kViewPageBytes"],
        "work": VIEW["kViewWorkBytes"],
    },
    words=("table", "pages"),
    thread=f"{STAGE}/thread/post_frame_words.c",
    begin=True,
)
