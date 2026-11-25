"""Texture pages gathered and filtered."""

from prism.core.implementation import IMPLEMENTATIONS, Implementation
from prism.stages.material.texture.check.thread_frame import check
from prism.stages.material.texture.device import made
from prism.stages.material.texture.host import TextureHost
from prism.stages.material.texture.unit import UNIT

TEXTURE = IMPLEMENTATIONS.register(
    "material.texture",
    Implementation(
        name="material.texture",
        fills=("material",),
        reads=("frame.visibility", "frame.lists"),
        writes=("mesh.attributes", "frame.surface"),
        device=made,
        host=TextureHost,
        check=check,
        thread=UNIT,
    ),
)
