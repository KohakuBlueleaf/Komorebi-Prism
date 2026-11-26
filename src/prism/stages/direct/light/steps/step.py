"""The direct light as a step of the tile thread: the surface and visibility planes
into the visibility's colour planes, the light pages on request, its kept table and
work, its words of the frame's page."""

from pathlib import Path

from prism.core import fields
from prism.core.headers import constexpr
from prism.core.thread.module import Step
from prism.stages.direct.light import device

KERNELS = Path(__file__).resolve().parent / "kernels"
LS = constexpr(KERNELS / "light_step.h")
STAGE = "stages/direct/light"


def table_bytes(held):
    """The kept table page: LIGHT's table, the camera, SHADE's table after them (the
    table field's bytes, light.h kShadeTableBytes) at the capacity `held`."""
    return 4 * max(fields.size("frame_table", held), device.TABLE_WORDS)


LIGHT = Step(
    name="light",
    header=f"{STAGE}/steps/kernels/light_step.hpp",
    requests=("pages",),
    reads=("frame.surface", "frame.visibility"),
    leaves=("frame.visibility",),
    keeps={
        "light_table": table_bytes,
        "light_work": LS["kLightStepWorkBytes"],
        "light_pages": LS["kLightStepPagesBytes"],
    },
    words=("table", "pages", "shade_table", "glass"),
    thread=f"{STAGE}/thread/light_frame_words.c",
)
