"""The sun's pass's thread unit: its C, the command it serves, its regions (the sun
region from the host, the times rows), the column naming LIGHT's table and the slot
that shares it, its build definitions."""

from prism.core.unit import Region, Unit
from prism.stages.direct.shadow_pcf.model.region import SUN_AT, times_bytes

UNIT = Unit(
    sources=("thread/direct_shadow_pcf_unit.c",),
    includes=("thread",),
    serves=("sun", "fit", "lamps"),
    regions={
        "sun": Region(
            lambda host: host.region_bytes(), lambda host: host.region(host.options)
        ),
        "sun_times": Region(lambda host: times_bytes(host.row_views())),
    },
    columns=("sun_table",),
    shares={"light.shadow_map": ("sun_table",)},
    gives={"light.shadow_maps": "shadow_maps"},
    defines=lambda host: {"SHADOW_PCF_SUN_AT": f"{SUN_AT}u"},
)
