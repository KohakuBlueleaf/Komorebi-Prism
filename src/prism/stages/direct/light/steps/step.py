"""The direct light as a step of the tile thread: the surface and visibility planes
into the first layer's colour planes, the light pages on request into the lit material
step's page cache, SHADE's table from the common field, its kept table, work and page
table, its words of the frame's page."""

from dataclasses import replace
from pathlib import Path

from prism.core.headers import constexpr
from prism.core.thread.module import Step
from prism.stages.material.texture.steps.step import SURFACE_PLANE
from prism.stages.raster.steps.step import VISIBILITY

KERNELS = Path(__file__).resolve().parent / "kernels"
LS = constexpr(KERNELS / "light_step.h")
STAGE = "stages/direct/light"
# the field's version as the frame's thread gives it (0 first: the table's own)
FIELD_WORDS = (
    "field_first",
    "field_unit_r",
    "field_unit_g",
    "field_unit_b",
    "field_scale",
)

LIGHT = Step(
    name="light",
    header=f"{STAGE}/steps/kernels/light_step.hpp",
    requests=("pages",),
    reads=(SURFACE_PLANE.name, VISIBILITY.name),
    leaves=(VISIBILITY.name,),
    keeps={
        "table": LS["kLightStepTableBytes"],
        "work": LS["kLightStepWorkBytes"],
        "pages": LS["kLightStepPagesBytes"] + LS["kLightStepAskedBytes"],
        "pass": LS["kLightStepPassBytes"],
    },
    words=("table", "pages", "glass", *FIELD_WORDS),
    thread=f"{STAGE}/thread/light_frame_words.c",
    begin=True,
    fields=("frame_table",),
)

# with the one-tile product: a row's I from the plane near.light when it is marked on
LIGHT_NEAR = replace(
    LIGHT,
    header=f"{STAGE}/steps/kernels/light_near_step.hpp",
    reads=(*LIGHT.reads, "near.light"),
)
