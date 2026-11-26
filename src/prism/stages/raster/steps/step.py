"""Visibility as a step of the tile thread: every layer's list walked as it streams,
each layer's planes filled with equal depths going to the lower triangle number."""

from prism.core.headers import INCLUDE, defined
from prism.core.thread.module import ListPass, Plane, Step
from prism.stages.raster.model.numbers import K

RECORD = defined(INCLUDE / "thread" / "record.h")
LAYERS = RECORD["TR_LAYERS"]  # the layers a record holds
PLANES = K["kPlanes"]  # a layer's pages: depth, red, green, blue, triangle
VISIBILITY = Plane("frame.visibility", "fp32", tiles=PLANES * LAYERS)


def every_layer(layers):
    """Every layer of the frame (its names), in layer order."""
    return tuple(range(len(layers)))


STEP = Step(
    name="visibility",
    header="stages/raster/steps/kernels/visibility.hpp",
    passes=(
        ListPass(
            layers=every_layer,
            block_records=K["kSlotsPerPage"],
            record_bytes=4 * K["kSlotWords"],
            page_records=K["kSlotsPerPage"],
        ),
    ),
    leaves=(VISIBILITY.name,),
    depth=True,
)
