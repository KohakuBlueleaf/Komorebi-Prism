"""The direct light's thread unit: LIGHT once a COLOUR view (twice with a glass layer),
its numbers (the surfaces' directories, the glass layer), the slots it takes (the
frame's directories, SHADE's table, LIGHT's table), its times, its forms and, with the
option light_shows, the bit its last colour LIGHT carries."""

from prism.core.unit import Unit
from prism.stages.direct.light.model.numbers import LH

FORMS = {"displayed": 0, "linear": LH["kLightLinear"], "glass": LH["kLightGlass"]}


def defines(host):
    """The forms as defines; with the option light_shows, DIRECT_LIGHT_SHOWN."""
    out = {f"DIRECT_LIGHT_{name.upper()}": f"{value}u" for name, value in FORMS.items()}
    if host.shows:
        out["DIRECT_LIGHT_SHOWN"] = f"{LH['kLightShown']}u"
    return out


UNIT = Unit(
    sources=("thread/direct_light_unit.c",),
    includes=("thread",),
    frame=True,
    takes=("frame.visibility", "mesh.attributes", "light.shadow_map"),
    numbers=("light_surface", "light_glass_surface", "light_glass"),
    times=("light", "light_glass"),
    defines=defines,
)
