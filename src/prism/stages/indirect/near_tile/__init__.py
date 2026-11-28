"""The near and far fields of the indirect light as one product a screen tile: W_T
built for a standing eye, held in the card's memory, a step of the tile thread."""

from prism.check.threads.whole import check
from prism.core.implementation import IMPLEMENTATIONS, Implementation
from prism.core.unit import Unit
from prism.stages.indirect.near_tile.host import NearTileHost

# the near tile step's numbers its frame words read (the records, the operands, the
# upsample's weights, the tables, the frame's half size, on)
UNIT = Unit(
    includes=("thread",),
    numbers=(
        "near_weights",
        "near_operand",
        "near_upsample",
        "near_table",
        "near_half",
        "near_on",
    ),
)

NEAR_TILE = IMPLEMENTATIONS.register(
    "indirect.near_tile",
    Implementation(
        name="indirect.near_tile",
        fills=(),
        reads=("view.camera",),
        writes=("near.weights",),
        device=None,
        host=NearTileHost,
        check=check,
        thread=UNIT,
    ),
)
