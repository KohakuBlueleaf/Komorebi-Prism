"""A scene's prepared lights: loading them with the table's numbers, the sun's angles,
and the lights of a moved sun."""

import numpy as np

from prism_reference.direct.shadow import shadow_map, sun_camera
from prism_reference.direct.sky import sh_turned
from prism_reference.post.tone import CURVE_PLAIN
from prism_reference.scene.public.lighting import lighting_path
from prism_reference.scene.public.table import is_view, public_dir, table, views

F = np.float32
# Indirect light: the bounce passes summed (a `lighting` entry's `bounces`).
BOUNCES = 2
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


def load(name, data):
    """The lights of a scene (or a view's scene): the arrays of LIGHT_KEYS, the table's
    numbers, the shadow bias as 1/z and the path of the indirect file when there is one.
    """
    if is_view(name):
        name = views()[name][0]
    path = lighting_path(name, data)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing; write it with: python scripts/data/public_scenes.py "
            f"lighting {name}"
        )
    with np.load(path) as f:
        lights = {k: f[k] for k in LIGHT_KEYS}
        lights["shadow_side"] = np.int32(
            f["shadow_side"] if "shadow_side" in f.files else len(f["shadow_map"])
        )
    entry = table()[name]["lighting"]
    distance = float(lights["shadow_texel"] * lights["shadow_camera"][12])
    bias = entry["shadow_bias"] * float(lights["shadow_texel"]) / distance**2
    numbers = {
        k: entry[k] for k in ("ambient", "emissive_scale", "exposure", "radius", "size")
    }
    numbers["reflection"] = entry.get("reflection", 0.0)
    numbers["saturation"] = entry.get("saturation", 1.0)
    numbers["curve"] = int(entry.get("curve", CURVE_PLAIN))
    numbers["bounces"] = bounce_count(entry.get("bounces", BOUNCES))
    found = public_dir(data) / f"{name}_indirect.npz"
    if found.exists():
        numbers["indirect"] = str(found)
    return lights | numbers | {"shadow_bias": F(bias)}
