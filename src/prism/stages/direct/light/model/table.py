"""LIGHT's table: the sky's products, ambient, sun, exposure, terms, lamps, shadow, turn,
the maps' pages, tone, each lamp and the field's words."""

import numpy as np

from prism.stages.direct.light.model.field import field_layout, field_words
from prism.stages.direct.light.model.numbers import F32, LH, PAGE
from prism.stages.direct.light.model.terms import term_bits
from prism.stages.material.texture.model.table import exponents
from prism_reference.direct.frame import TERMS
from prism_reference.direct.glass import GLASS_F0
from prism_reference.direct.lights import shadow_side
from prism_reference.direct.sky import C1, C2, C3, C4, C5
from prism_reference.post.tone import CURVE_FILMIC, CURVE_PLAIN
from prism_reference.raster.fill import BACKGROUND


def light_table(lights, materials, terms=TERMS, field=None, indirect=True):
    """LIGHT's table (shade.h kLt*): the sky, ambient, sun, exposure, terms, lamps,
    shadow, turn, maps' pages, tone (saturation 1 and curve 0 when the lights lack
    them), each lamp; with the term `indirect` the field's words (`field`: field_of,
    its pages from its `half` of its `halves`, 0 of 1 when absent), `indirect` False
    clearing kTermIndirect."""
    words = np.zeros(LH["kLightTableBytes"] // 4, dtype=np.uint32)

    def put(at, values):
        values = np.atleast_1d(np.asarray(values, dtype=F32))
        words[at : at + len(values)] = values.view(np.uint32)

    s = lights["sh"].astype(F32)
    two_c1, two_c2 = F32(2) * C1, F32(2) * C2
    for channel in range(3):
        k = s[:, channel]
        sky = [
            C4 * k[0] - C5 * k[6],
            C3 * k[6],
            C1 * k[8],
            two_c1 * k[4],
            two_c1 * k[7],
            two_c1 * k[5],
            two_c2 * k[3],
            two_c2 * k[1],
            two_c2 * k[2],
        ]
        at = LH["kLtChannel"] * channel
        put(at + LH["kLtSky"], sky)
        put(at + LH["kLtAmbient"], lights["ambient"][channel])
        put(at + LH["kLtSun"], lights["sun_irradiance"][channel])
    put(LH["kLtSunDirection"], lights["sun_direction"])
    exposure = F32(lights["exposure"])
    put(LH["kLtExposure"], exposure)
    put(LH["kLtScale"], exposure * F32(1 / np.pi))
    put(LH["kLtBackground"], BACKGROUND)
    put(LH["kLtInvPi"], F32(1 / np.pi))
    words[LH["kLtTerms"]] = term_bits(terms)
    if not indirect:
        words[LH["kLtTerms"]] &= ~np.uint32(LH["kTermIndirect"])
    saturation, curve = F32(lights.get("saturation", 1.0)), lights.get("curve", 0)
    if curve not in (CURVE_PLAIN, CURVE_FILMIC):
        raise ValueError(f"tone curve {curve}: 0 (plain) or 1 (filmic)")
    put(LH["kLtSaturation"], saturation)
    words[LH["kLtCurve"]] = int(curve)
    words[LH["kLtExponentBits"]] = int(exponents(materials).max(initial=0)).bit_length()
    lamps = len(lights["lamp_intensity"]) if "lamps" in terms else 0
    if lamps > LH["kLampsMax"]:
        raise ValueError(f"{lamps} lamps: LIGHT's table holds {LH['kLampsMax']}")
    words[LH["kLtLamps"]] = lamps
    put(LH["kLtShadowTexel"], lights["shadow_texel"])
    put(LH["kLtShadowBias"], lights["shadow_bias"])
    put(LH["kLtShadowCamera"], lights["shadow_camera"])
    # the background's view direction turned by -turn about y
    angle = np.radians(-float(lights["turn"]))
    put(LH["kLtTurnCos"], F32(np.cos(angle)))
    put(LH["kLtTurnSin"], F32(np.sin(angle)))
    # light_pages' layout from the maps' sides
    sides = {"Shadow": shadow_side(lights), "Octa": lights["octahedral"].shape[0]}
    shadow_pages = (sides["Shadow"] // PAGE) ** 2
    first = {"Shadow": 0, "Octa": shadow_pages}
    pages = shadow_pages + 3 * (sides["Octa"] // PAGE) ** 2
    for name, side in sides.items():
        put(LH[f"kLt{name}First"], 1 + first[name])
        put(LH[f"kLt{name}Across"], side // PAGE)
        put(LH[f"kLt{name}Side"], side)
    put(LH["kLtOctaLast"], lights["octahedral"].shape[0] - 1)
    words[LH["kLtOctaChannel"]] = (lights["octahedral"].shape[0] // PAGE) ** 2 << 10
    if "indirect" in terms:
        if field is None:
            raise ValueError("the term indirect needs the field (light.field_of)")
        count = field_layout(field["model"])[1]
        field_words(words, field, pages + field.get("half", 0) * count)
        pages += field.get("halves", 1) * count
    words[LH["kLtPages"]] = pages
    # the glass's reflection: its share, F0 and 1 - F0
    put(LH["kLtReflection"], lights.get("reflection", 0.0))
    put(LH["kLtFresnel0"], GLASS_F0)
    put(LH["kLtFresnelRest"], F32(1) - GLASS_F0)
    radius, size = F32(lights["radius"]), F32(lights["size"])
    for lamp in range(lamps):
        at = LH["kLtLamp"] + LH["kLampWords"] * lamp
        put(at, lights["lamp_position"][lamp])
        put(at + LH["kLampColour"], lights["lamp_colour"][lamp])
        put(at + LH["kLampIntensity"], lights["lamp_intensity"][lamp])
        put(at + LH["kLampRadius"], radius)
        put(at + LH["kLampInvRadius"], F32(1) / radius)
        put(at + LH["kLampSize2"], size**2)
    return words
