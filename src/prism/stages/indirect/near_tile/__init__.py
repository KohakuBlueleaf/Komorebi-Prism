"""The near and far fields of the indirect light as one product a screen tile: W_T
built for a standing eye, held in the card's memory, a step of the tile thread."""

from prism.check.threads.whole import check
from prism.core.implementation import IMPLEMENTATIONS, Implementation
from prism.stages.indirect.near_tile.host import NearTileHost

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
    ),
)
