"""The direct light's thread unit in the threads' form (the light step's frame words
read it; the tile thread builds their C): its numbers (the light pages, the glass
layer, the field's first page and pages), the slot it takes for LIGHT's table and, with
the job thread, the slots that give the field's version."""

from dataclasses import replace

from prism.core.unit import Unit
from prism_reference.indirect.field.pack import PACK_BITS

CHANNELS = ("R", "G", "B")


def defines(host):
    """The field's code bits a channel (its units' denominators)."""
    return {
        f"DIRECT_LIGHT_FIELD_BITS_{name}": f"{bits}u"
        for name, bits in zip(CHANNELS, PACK_BITS, strict=True)
    }


def field_defines(host):
    """As `defines`, and the field's version taken from the thread's slots."""
    return defines(host) | {"DIRECT_LIGHT_FIELD_BY_SLOT": "1"}


UNIT = Unit(
    takes=("light.shadow_map",),
    numbers=("light_pages", "light_glass", "light_field_first", "light_field_pages"),
    defines=defines,
)

# with the job thread: the field's half (1 + it; 0 none yet) and scale word by slots
FIELD_UNIT = replace(
    UNIT,
    takes=("light.shadow_map", "light.field", "light.field_scale"),
    defines=field_defines,
)
