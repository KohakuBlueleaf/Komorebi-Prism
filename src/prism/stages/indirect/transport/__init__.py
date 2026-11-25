"""The far field: the hierarchical transport matrix applied, y = M x on every core."""

from prism.core.implementation import IMPLEMENTATIONS, Implementation
from prism.stages.indirect.transport.check import check
from prism.stages.indirect.transport.device import made
from prism.stages.indirect.transport.host import TransportHost
from prism.stages.indirect.transport.unit import UNIT

TRANSPORT = IMPLEMENTATIONS.register(
    "indirect.transport",
    Implementation(
        name="indirect.transport",
        fills=("indirect",),
        reads=("elements.radiance",),
        writes=("elements.irradiance",),
        device=made,
        host=TransportHost,
        check=check,
        thread=UNIT,
    ),
)
