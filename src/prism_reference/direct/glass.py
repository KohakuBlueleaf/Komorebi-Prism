"""Glass in the lit frame: what is behind it, its own light and the environment it
reflects."""

import numpy as np

from prism_reference.direct.sky import environment_radiance
from prism_reference.raster.setup import world_points
from prism_reference.raster.vector import dot3, normalized

F = np.float32
GLASS_F0 = F(0.04)  # the glass's reflectance facing the eye (Schlick's F0)


def glass_over(scene, lights, glass, parts, front, behind, terms):
    """The colour where the glass is in front: tau C + its own (1 - max tau) a / pi E
    + S (`behind`: C, own, tau) + F x reflection x the environment along the mirror."""
    ys, xs = np.nonzero(front)
    px, py = xs.astype(np.float32) + F(0.5), ys.astype(np.float32) + F(0.5)
    cam = scene["camera"]
    position = world_points(cam, px, py, glass["depth"][ys, xs])
    to_eye = normalized(cam[None, 0:3] - position)
    normal = parts["normal"][ys, xs]
    facing = np.maximum(dot3(normal, to_eye), F(0))
    q = F(1) - facing
    fresnel = GLASS_F0 + (F(1) - GLASS_F0) * (((q * q) * (q * q)) * q)
    mirror = normal * (F(2) * facing)[:, None] - to_eye
    reflection = F(lights.get("reflection", 0.0))
    shine = np.zeros((len(ys), 3), dtype=np.float32)
    if "background" in terms and reflection > 0:
        shine = (fresnel * reflection)[:, None] * environment_radiance(lights, mirror)
    colour, own, tau = behind
    out = colour.copy()
    seen = tau[ys, xs] * colour[ys, xs]
    out[ys, xs] = (seen + own[ys, xs]) + shine
    return out
