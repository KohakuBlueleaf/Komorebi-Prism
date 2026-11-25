"""The indirect field updated after a light change: the sources from the sun's shadow
map and the elements, the bounce passes (each the transport's apply), the field's
values by row and its pages."""

from prism.core.implementation import IMPLEMENTATIONS, Implementation
from prism.stages.indirect.field_update.check import check
from prism.stages.indirect.field_update.host import FieldUpdateHost
from prism.stages.indirect.field_update.unit import UNIT

FIELD_UPDATE = IMPLEMENTATIONS.register(
    "indirect.field_update",
    Implementation(
        name="indirect.field_update",
        fills=(),
        reads=("elements.irradiance", "elements.radiance", "light.shadow_map"),
        writes=("light.field",),
        device=None,
        host=FieldUpdateHost,
        check=check,
        thread=UNIT,
    ),
)
