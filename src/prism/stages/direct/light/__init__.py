"""Analytic lights with the BRDF."""

from prism.core.implementation import IMPLEMENTATIONS, Implementation
from prism.stages.direct.light.check.thread_frame import check
from prism.stages.direct.light.device import made
from prism.stages.direct.light.host import LightHost
from prism.stages.direct.light.unit import UNIT

LIGHT = IMPLEMENTATIONS.register(
    "direct.light",
    Implementation(
        name="direct.light",
        fills=("direct",),
        reads=(
            "frame.visibility",
            "mesh.attributes",
            "light.shadow_map",
            "light.transmit",
            "frame.surface",
        ),
        writes=("frame.visibility",),
        device=made,
        host=LightHost,
        check=check,
        thread=UNIT,
    ),
)
