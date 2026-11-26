"""The transport's thread unit: its C, the slot it gives (one apply), the command it
serves, its number (the group's cores), its results region, its cluster the host's."""

from pathlib import Path

from prism.core.headers import defined
from prism.core.unit import Region, Unit

THREAD = "thread"
R = defined(Path(__file__).resolve().parent / THREAD / "indirect_transport_unit.h")

UNIT = Unit(
    sources=(f"{THREAD}/indirect_transport_unit.c",),
    includes=(THREAD,),
    serves=("apply",),
    gives={"elements.irradiance": "pass"},
    regions={"transport_results": Region(4 * R["TRANSPORT_R_WORDS"], own=False)},
    numbers=("transport_cores",),
    cluster=lambda host: host.cluster,
)
