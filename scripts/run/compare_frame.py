"""The reference's whole frame of an opened scene for `compare.py`: the preset's lit frame
(`prism_reference.direct.frame`, the lights of the scene's lighting file) with its terms,
without the term indirect, and its indirect split into the bounces and the sky's own
light; the card's linear colour from its picture."""

import numpy as np
from prism_cli.preset import opened

from prism.stages.direct.light.model.expect import with_map
from prism_reference.direct.frame import rasterize_lighted
from prism_reference.direct.lights import BOUNCES, bounce_count
from prism_reference.direct.lights import load as load_lights
from prism_reference.indirect.field.values import field_values
from prism_reference.indirect.files import load_model
from prism_reference.indirect.light import element_light, signature
from prism_reference.post.display import GAMMA, to_srgb8
from prism_reference.post.tone import CURVE_PLAIN
from prism_reference.raster.frames import picture
from prism_reference.scene.artist.entry import VIEW
from prism_reference.scene.camera import with_size

INDIRECT = "indirect"
REPLACED = ("sky", "ambient")  # the terms the frame lights with in the indirect's place
TOP = 254.5 / 255.0  # a display value at or past it: clipped, not inverted
LIGHTS = "converter"  # whose lights the frame is lit by: the conversion's lighting file


def bounces_only(lights):
    """`lights` whose field holds the bounce passes alone (not the elements' own sky
    irradiance) and no ambient where no voxel has data: a field entered under its key.
    """
    model = load_model(lights["indirect"])
    bounces = bounce_count(lights.get("bounces", BOUNCES))
    light = element_light(lights, model, bounces)
    source = sum(light["passes"], np.zeros_like(light["sky"]))
    own = {**lights, "shadow_map": np.array(lights["shadow_map"], copy=True)}
    own["ambient"] = np.zeros(3, np.float32)
    key = (signature(own), id(own["shadow_map"]), id(own["octahedral"]), bounces)
    entry = (key, own["shadow_map"], field_values(model, source))
    model.setdefault("cache", []).append(entry)
    return own


def frame_of(pipeline, name, size, data):
    """{"display": bytes, "colour": linear, "off": linear without the term indirect (the
    sky and ambient in its place), "direct": without those three, "bounces" and "sky"
    (the indirect term's two parts; None without the term), "lit", "tone", "far_field",
    "lights"} of the preset's reference frame of `name` at `size`."""
    preset = opened(pipeline, name, VIEW, tuple(size))
    view = with_size(preset.scene, size)
    options = preset.options
    materials = options["materials"]
    lights = load_lights(name, data)
    if "bounces" in options:
        lights = {**lights, "bounces": options["bounces"]}
    lights = with_map(view, materials, lights)
    terms = tuple(options.get("terms", ()))
    lit = rasterize_lighted(view, materials, lights, terms=terms)
    out = {"display": to_srgb8(picture(lit["display"], view))}
    out["colour"] = picture(lit["colour"], view)
    out["tone"] = {
        "exposure": float(lights["exposure"]),
        "saturation": float(lights.get("saturation", 1.0)),
        "curve": int(lights.get("curve", CURVE_PLAIN)),
    }
    out["far_field"], out["lights"] = preset.far_field, LIGHTS
    out |= {"off": None, "direct": None, "bounces": None, "sky": None}
    parts = lit["parts"]
    out["lit"] = picture(parts["sun"] + parts["points"], view)
    if INDIRECT in terms:
        without = tuple(t for t in terms if t != INDIRECT)
        alone = tuple(t for t in without if t not in REPLACED)
        for part, chosen in (("off", without), ("direct", alone)):
            lit = rasterize_lighted(view, materials, lights, terms=chosen)
            out[part] = picture(lit["colour"], view)
        bounced = rasterize_lighted(view, materials, bounces_only(lights), terms=terms)
        bounced = picture(bounced["colour"], view)
        out["bounces"] = bounced - out["direct"]
        out["sky"] = out["colour"] - bounced
    return out


def card_linear(picture_bytes, tone):
    """The card's linear colour from its display bytes under `tone` (the plain curve,
    saturation 1): the 1/GAMMA power and x / (1 + x) undone, over exposure; None for
    another tone. Clipped values are kept at TOP."""
    if (
        picture_bytes is None
        or tone is None
        or tone["curve"] != CURVE_PLAIN
        or tone["saturation"] != 1.0
    ):
        return None
    y = np.minimum((picture_bytes.astype(np.float64) / 255.0) ** GAMMA, TOP)
    return y / (1.0 - y) / tone["exposure"]
