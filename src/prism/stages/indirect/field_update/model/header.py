"""The header region's words: the counts and the arrays' offsets at the load, the sun's
words written on each change."""

import numpy as np

from prism.stages.indirect.field_update.model.numbers import (
    F32,
    HEADER_BYTES,
    PAGE_TEXELS,
    SUN_FIRST,
    SUN_WORDS,
    X_PAGE,
    Y_PAGE,
    H,
    places,
)
from prism.stages.indirect.field_update.model.regions import counts
from prism_reference.direct.lights import bounce_count, shadow_side
from prism_reference.indirect.sky import sky_coefficients

SUN, SUN_COUNT = places(SUN_WORDS)


def sun_words(lights, bounces):
    """The update's inputs of `lights` (sun_lights'), the header's words from
    `bounces` on, as uint32: the passes, the shadow texel and bias, the sun's direction
    and irradiance, its camera, the sky's 25 x 3 coefficients."""
    words = np.zeros(SUN_COUNT, dtype=np.uint32)

    def put(name, values):
        values = np.atleast_1d(np.asarray(values, dtype=F32)).ravel()
        words[SUN[name] : SUN[name] + len(values)] = values.view(np.uint32)

    words[SUN["bounces"]] = bounce_count(bounces)
    put("texel", lights["shadow_texel"])
    put("bias", lights["shadow_bias"])
    put("sun", lights["sun_direction"])
    put("irradiance", lights["sun_irradiance"])
    put("camera", lights["shadow_camera"])
    put("sky", sky_coefficients(lights))
    return words


def header(model, lights, offsets, bounces):
    """The header region (uint32 [HEADER_BYTES / 4]) at the load: the counts, the
    shadow map's pages and side, the pages' bytes, the arrays' offsets (`offsets`, by
    header word), the sun's words of `lights`."""
    c = counts(model)
    words = np.zeros(HEADER_BYTES // 4, dtype=np.uint32)
    side = shadow_side(lights)
    values = {
        "n": c["n"],
        "tiles": c["tiles"],
        "rows": c["rows"],
        "weights": c["weights"],
        "pages": c["pages"],
        "shadow_pages": side * side // PAGE_TEXELS,
        "side": side,
        "x_page": X_PAGE,
        "y_page": Y_PAGE,
        **offsets,
    }
    for name, value in values.items():
        words[H[name]] = value
    sun = sun_words(lights, bounces)
    words[SUN_FIRST : SUN_FIRST + len(sun)] = sun
    return words
