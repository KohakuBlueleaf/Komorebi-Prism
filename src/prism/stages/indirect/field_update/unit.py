"""The field update's thread unit: its C, the commands it serves (update, field_scale),
the slot it takes (a pass's apply), its regions from the host's model and lights, its
numbers, its defines (the header's word places)."""

import numpy as np

from prism.core.unit import Region, Unit
from prism.stages.indirect.field_update.model.numbers import (
    HEADER_BYTES,
    NUMBERS,
    PAGE_BYTES,
    PAGE_TEXELS,
    TIMES_BYTES,
    header_defines,
)
from prism_reference.direct.lights import shadow_side

UNIT = Unit(
    sources=(
        "thread/indirect_field_update_unit.c",
        "thread/indirect_field_update_parts.c",
    ),
    includes=("thread",),
    serves=("update", "field_scale"),
    takes=("elements.irradiance",),
    regions={
        "field_header": Region(
            HEADER_BYTES, lambda host: host.header_words(), own=False
        ),
        "field_elements": Region(
            lambda host: host.elements.nbytes,
            lambda host: host.elements.view(np.uint32),
        ),
        "field_shadow": Region(
            lambda host: shadow_side(host.lights) ** 2 * PAGE_BYTES // PAGE_TEXELS
        ),
        "field_work": Region(lambda host: host.work_bytes),
        "field_pages": Region(lambda host: host.counts["pages"] * PAGE_BYTES),
        "field_times": Region(TIMES_BYTES),
    },
    numbers=NUMBERS,
    defines=lambda host: header_defines(),
)
