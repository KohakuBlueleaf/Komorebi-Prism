"""The sun's pass's thread unit: its C, the command it serves, its regions (the sun
region from the host, the times rows), the column naming LIGHT's table and the slot
that shares it, its build definitions."""

from prism.core.unit import Region, Unit
from prism.stages.direct.shadow_pcf.model.region import (
    SUN_AT,
    region_bytes,
    times_bytes,
)

UNIT = Unit(
    sources=("thread/direct_shadow_pcf_unit.c",),
    includes=("thread",),
    serves=("sun",),
    regions={
        "sun": Region(
            lambda host: region_bytes(len(host.views)),
            lambda host: host.region(host.options),
        ),
        "sun_times": Region(lambda host: times_bytes(len(host.views))),
    },
    columns=("sun_table",),
    shares={"light.shadow_map": ("sun_table",)},
    defines=lambda host: {"SHADOW_PCF_SUN_AT": f"{SUN_AT}u"},
)
