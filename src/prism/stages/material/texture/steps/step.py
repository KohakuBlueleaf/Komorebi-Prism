"""Material as a step of the tile thread, unlit or lit: the layers' lists walked again
in SHADE's order, texture pages requested, the colour (unlit) or the frame's words and
the surfaces (lit) left in the tile's planes."""

from dataclasses import replace
from pathlib import Path

from prism.core.headers import constexpr
from prism.core.thread.module import ListPass, Plane, Step
from prism.stages.direct.light.model.numbers import LH
from prism.stages.material.texture.model.numbers import PAGES, SH, SURFACE
from prism.stages.raster.model.numbers import K
from prism.stages.raster.steps.step import VISIBILITY

KERNELS = Path(__file__).resolve().parent / "kernels"
LIT = constexpr(KERNELS / "lit" / "lit.hpp")
RUN = constexpr(KERNELS / "run.hpp")
WORD = 4  # bytes a word
SURFACE_PLANE = Plane(
    "frame.surface", "fp32", tiles=SURFACE["kSurfacePlanes"] * LIT["kSurfaces"]
)
ORDER = ("opaque", "masked", "glass")  # the layers in the order SHADE walks them


def shaded_layers(layers):
    """The indices of the frame's layers (their names) in SHADE's order."""
    names = list(layers)
    return tuple(names.index(name) for name in ORDER if name in names)


PASS = ListPass(
    layers=shaded_layers,
    block_records=K["kSlotsPerPage"],
    record_bytes=WORD * K["kSlotWords"],
    page_records=K["kSlotsPerPage"],
)
CACHE_BYTES = (PAGES["kShadeSlots"] + 1) * SURFACE["kTexPageBytes"]  # and the white
KEEPS = {
    "work": SH["kShadeWorkBytes"],
    "cache": CACHE_BYTES,
    "run": RUN["kRunBytes"],  # the pack CPU's state of a tile thread
}
LIT_KEEPS = {
    "lit_work": LH["kLightWorkBytes"],
    "camera": SH["kCamWordsShade"] * WORD,  # the view's camera, the loop's to fill
}
WORDS = ("layers", "textures", "table")
THREAD = "stages/material/texture/steps/thread/material_frame_words.c"
FIELDS = ("frame_table",)  # SHADE's table, read by the step's begin

STEP = Step(
    name="material",
    header="stages/material/texture/steps/kernels/material.hpp",
    passes=(PASS,),
    requests=("texture",),
    reads=(VISIBILITY.name,),
    leaves=(VISIBILITY.name,),
    keeps=KEEPS,
    words=WORDS,
    thread=THREAD,
    begin=True,
    fields=FIELDS,
)

LIT_STEP = Step(
    name="material_lit",
    header="stages/material/texture/steps/kernels/material.hpp",
    passes=(PASS,),
    requests=("texture",),
    reads=(VISIBILITY.name,),
    leaves=(VISIBILITY.name, SURFACE_PLANE.name),
    keeps=KEEPS | LIT_KEEPS,
    words=WORDS,
    thread=THREAD,
    begin=True,
    fields=FIELDS,
    depth=True,
)

# with the sun map's T (the option shadow_transmit): a DEPTH view's glass layer's T
LIT_TRANSMIT_STEP = replace(
    LIT_STEP, header="stages/material/texture/steps/kernels/material_transmit.hpp"
)
