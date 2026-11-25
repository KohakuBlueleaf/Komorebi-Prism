"""The direct light's thread unit: LIGHT once a COLOUR view (twice with a glass layer),
its numbers (the surfaces' directories, the glass layer), the slots it takes (the
frame's directories, SHADE's table, LIGHT's table), its times and its forms."""

from prism.core.unit import Unit
from prism.stages.direct.light.model.numbers import LH

FORMS = {"displayed": 0, "linear": LH["kLightLinear"], "glass": LH["kLightGlass"]}

UNIT = Unit(
    sources=("thread/direct_light_unit.c",),
    includes=("thread",),
    frame=True,
    takes=("frame.visibility", "mesh.attributes", "light.shadow_map"),
    numbers=("light_surface", "light_glass_surface", "light_glass"),
    times=("light", "light_glass"),
    defines=lambda host: {
        f"DIRECT_LIGHT_{name.upper()}": f"{value}u" for name, value in FORMS.items()
    },
)
