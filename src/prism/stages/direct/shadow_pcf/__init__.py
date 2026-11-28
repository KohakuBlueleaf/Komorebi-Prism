"""Shadow visibility by depth comparison and averaging: the sun's shadow map drawn by
DEPTH views of the frame's units, a quadrant a view."""

from prism.core.implementation import IMPLEMENTATIONS, Implementation
from prism.stages.direct.shadow_pcf.check.sun_map import check
from prism.stages.direct.shadow_pcf.host import ShadowHost
from prism.stages.direct.shadow_pcf.unit import UNIT

SHADOW_PCF = IMPLEMENTATIONS.register(
    "direct.shadow_pcf",
    Implementation(
        name="direct.shadow_pcf",
        fills=(),
        reads=("scene.mesh",),
        writes=(
            "light.shadow_map",
            "light.shadow_maps",
            "light.lamp_faces",
            "light.transmit",
            "view.depth",
        ),
        device=None,
        host=ShadowHost,
        check=check,
        thread=UNIT,
    ),
)
