"""A scene's prepared lights: loading them with the table's numbers, the sun's angles,
and the lights of a moved sun."""

import numpy as np

from prism_reference.direct.lamps import without_areas
from prism_reference.direct.shadow import shadow_map, sun_camera
from prism_reference.direct.sky import sh_turned
from prism_reference.post.tone import CURVE_PLAIN
from prism_reference.scene.public.lighting import lighting_path
from prism_reference.scene.public.table import is_view, public_dir, table, views

F = np.float32
FILE_LIGHTS = "file_lights"  # the option that draws a file's own lights and world
AREA_LIGHTS = "area_lights"  # with it, the option that keeps the area lights' stand-ins
FILE = "file_"  # the lighting file's arrays of the file's own lighting
# Indirect light: the bounce passes summed (a `lighting` entry's `bounces`); None: the
# scene's own (prism_reference.indirect.bounces)
BOUNCES = None
LIGHT_KEYS = (
    "visibility",
    "sh",
    "sun_direction",
    "sun_irradiance",
    "octahedral",
    "turn",
    "shadow_map",
    "shadow_camera",
    "shadow_texel",
    "lamp_position",
    "lamp_colour",
    "lamp_intensity",
)


def sun_angles(direction):
    """Azimuth and elevation (degrees) of a direction toward the sun: azimuth 0 at +x,
    90 at -z, elevation above the horizontal plane (y = 0)."""
    d = np.asarray(direction, np.float64)
    elevation = np.degrees(np.arctan2(d[1], np.hypot(d[0], d[2])))
    return float(np.degrees(np.arctan2(-d[2], d[0]))), float(elevation)


def sun_direction(azimuth, elevation):
    """The unit direction (3,) float32 toward a sun at azimuth, elevation (degrees,
    as `sun_angles`)."""
    a, e = np.radians(azimuth), np.radians(elevation)
    return np.array(
        [np.cos(e) * np.cos(a), np.sin(e), -np.cos(e) * np.sin(a)], dtype=np.float32
    )


def shadow_side(lights):
    """The shadow map's side of prepared lights: their `shadow_side`, else the map's."""
    if "shadow_side" in lights:
        return int(lights["shadow_side"])
    return int(lights["shadow_map"].shape[0])


def placeholder(lights):
    """Whether prepared lights hold a placeholder shadow map (smaller than their
    `shadow_side`): the card renders the map."""
    return int(lights["shadow_map"].shape[0]) != shadow_side(lights)


def moved(lights, scene, materials, azimuth, elevation):
    """The prepared lights with the sun at azimuth, elevation (degrees): the map turned
    with it, the shadow map rebuilt; elevation <= 0: no sun, a 1 x 1 map of 0."""
    own_azimuth, _ = sun_angles(lights["sun_direction"])
    change = float(azimuth) - own_azimuth
    sun = sun_direction(azimuth, elevation)
    out = dict(lights)
    out["turn"] = np.float32(float(lights["turn"]) + change)
    out["sh"] = sh_turned(lights["sh"], change)
    out["sun_direction"] = sun
    # The bias in shadow texels at the camera's distance, as `load` made it.
    distance = float(lights["shadow_texel"] * lights["shadow_camera"][12])
    texels = float(lights["shadow_bias"]) * distance**2 / float(lights["shadow_texel"])
    side = shadow_side(lights)
    out["shadow_side"] = np.int32(side)
    if elevation <= 0:
        camera = sun_camera(scene["positions"], sun, side)
        out["sun_irradiance"] = np.zeros(3, dtype=np.float32)
        out["shadow_map"] = np.zeros((1, 1), dtype=np.float32)
        out["shadow_camera"], out["shadow_texel"] = camera, lights["shadow_texel"]
        return out
    depth, camera, texel = shadow_map(scene, sun, materials, side)
    out["shadow_map"], out["shadow_camera"], out["shadow_texel"] = depth, camera, texel
    distance = float(texel * camera[12])
    out["shadow_bias"] = F(texels * float(texel) / distance**2)
    return out


def bounce_count(value):
    """A number of bounce passes: a whole number 0 or more; else ValueError with the
    reason."""
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise ValueError(  # noqa: TRY004
            f"bounces is a whole number 0 or more, not {value!r}"
        )
    if int(value) < 0:
        raise ValueError(f"bounces is 0 or more, not {int(value)}")
    return int(value)


def options_of(options):
    """The loader's file_lights and area_lights from a run's `options`."""
    return bool(options.get(FILE_LIGHTS, False)), bool(options.get(AREA_LIGHTS, False))


def file_lights(f, entry, area_lights):
    """The file's own lighting of the lighting file `f` (its `file_` arrays in place of
    LIGHT_KEYS', `lamp_shape`, the area lights' stand-ins only with `area_lights`) and
    its entry's numbers (the table's `file` over the defaults'); ValueError when the
    scene has none."""
    if "file" not in entry or f"{FILE}lamp_shape" not in f.files:
        raise ValueError(
            "the option file_lights: the scene has no lighting of its own in its "
            "lighting file (convert it again)"
        )
    lights = {k: f[k] for k in LIGHT_KEYS}
    lights |= {k[len(FILE) :]: f[k] for k in f.files if k.startswith(FILE)}
    lights.pop("counts")
    if not area_lights:
        lights = without_areas(lights)
    return lights, entry | entry["file"]


def load(name, data, file_lights_on=False, area_lights=False):
    """The lights of a scene (or a view's scene): the arrays of LIGHT_KEYS, the table's
    numbers, the shadow bias as 1/z and the path of the indirect file when there is one;
    with `file_lights_on` the file's own lighting (`file_lights`) and its numbers."""
    if is_view(name):
        name = views()[name][0]
    path = lighting_path(name, data)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing; write it with: python scripts/data/public_scenes.py "
            f"lighting {name}"
        )
    entry = table()[name]["lighting"]
    with np.load(path) as f:
        lights = {k: f[k] for k in LIGHT_KEYS}
        if file_lights_on:
            lights, entry = file_lights(f, entry, area_lights)
        lights["shadow_side"] = np.int32(
            f["shadow_side"] if "shadow_side" in f.files else len(f["shadow_map"])
        )
    distance = float(lights["shadow_texel"] * lights["shadow_camera"][12])
    bias = entry["shadow_bias"] * float(lights["shadow_texel"]) / distance**2
    numbers = {
        k: entry[k] for k in ("ambient", "emissive_scale", "exposure", "radius", "size")
    }
    numbers["reflection"] = entry.get("reflection", 0.0)
    numbers["saturation"] = entry.get("saturation", 1.0)
    numbers["curve"] = int(entry.get("curve", CURVE_PLAIN))
    given = entry.get("bounces", BOUNCES)
    numbers["bounces"] = None if given is None else bounce_count(given)
    found = public_dir(data) / f"{name}_indirect.npz"
    if found.exists():
        numbers["indirect"] = str(found)
    return lights | numbers | {"shadow_bias": F(bias)}
