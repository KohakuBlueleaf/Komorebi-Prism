"""Glass in the lit frame: what is behind it, its own light, what it reflects and the
sun it lets through."""

import numpy as np

from prism_reference.direct.shadow import FILL_SIDE, quadrant_camera, sun_screen
from prism_reference.direct.sky import environment_radiance, sky_irradiance
from prism_reference.material.kinds import TRANSPARENT
from prism_reference.raster.frames import layer_scene, rasterize
from prism_reference.raster.setup import world_points
from prism_reference.raster.vector import dot3, normalized

F = np.float32
GLASS_F0 = F(0.04)  # a dielectric glass's reflectance facing the eye (Schlick's F0)
NO_GLASS = F(0)  # a glass map texel's 1/z where no glass faces the sun
GLASS_LIGHT = "glass_light"  # the term: the glass's shadow, F0 and reflected radiance


def reflected(lights, position, mirror, terms, field):
    """Radiance (n, 3) the glass reflects along `mirror`: the environment's (times the
    lights' "reflection") when given, else field(position, mirror) / pi, else the
    sky's irradiance / pi."""
    reflection = F(lights.get("reflection", 0.0))
    if "background" in terms and reflection > 0:
        return reflection * environment_radiance(lights, mirror)
    if field is not None:
        return field(position, mirror) * F(1 / np.pi)
    return np.maximum(sky_irradiance(lights["sh"], mirror), F(0)) * F(1 / np.pi)


def glass_over(scene, lights, glass, parts, front, behind, terms, field=None):
    """The colour where the glass is in front: tau C + its own (1 - max tau) a / pi E +
    S (`behind`: C, own, tau) + F x reflection x the environment along the mirror (F
    Schlick's of F0 GLASS_F0); with the term GLASS_LIGHT, tau (1 - (F - F0)) C + own + S
    + F x the radiance it reflects (`reflected`), F0 its specular colour."""
    ys, xs = np.nonzero(front)
    px, py = xs.astype(np.float32) + F(0.5), ys.astype(np.float32) + F(0.5)
    cam = scene["camera"]
    position = world_points(cam, px, py, glass["depth"][ys, xs])
    to_eye = normalized(cam[None, 0:3] - position)
    normal = parts["normal"][ys, xs]
    facing = np.maximum(dot3(normal, to_eye), F(0))
    q = F(1) - facing
    lit = GLASS_LIGHT in terms
    f0 = parts["specular"][ys, xs] if lit else np.full((len(ys), 3), GLASS_F0)
    fresnel = f0 + (F(1) - f0) * (((q * q) * (q * q)) * q)[:, None]
    mirror = normal * (F(2) * facing)[:, None] - to_eye
    colour, own, tau = behind
    seen = tau[ys, xs] * colour[ys, xs]
    if lit:
        shine = fresnel * reflected(lights, position, mirror, terms, field)
        seen = seen * (F(1) - (fresnel - f0))
    else:
        shine = np.zeros((len(ys), 3), dtype=np.float32)
        reflection = F(lights.get("reflection", 0.0))
        if "background" in terms and reflection > 0:
            radiance = environment_radiance(lights, mirror)
            shine = (fresnel[:, 0] * reflection)[:, None] * radiance
    out = colour.copy()
    out[ys, xs] = (seen + own[ys, xs]) + shine
    return out


def sun_glass_map(scene, materials, lights):
    """{"depth": 1/z (side, side) of the glass nearest the sun (NO_GLASS where none),
    "shadow": the direct light it lets through (side, side, 3)} from the lights' shadow
    camera, rendered in quadrants of FILL's frame as the shadow map is."""
    camera = lights["shadow_camera"]
    side = lights["shadow_map"].shape[0]
    kind = materials["kind"][materials["material"]]
    clear = kind == TRANSPARENT
    through = materials["shadow"]
    depth = np.full((side, side), NO_GLASS, dtype=np.float32)
    shadow = np.ones((side, side, 3), dtype=np.float32)
    for j in range(side // FILL_SIDE):
        for i in range(side // FILL_SIDE):
            view = {
                "positions": scene["positions"],
                "indices": scene["indices"],
                "colors": np.zeros((len(scene["positions"]), 3), dtype=np.float32),
                "camera": quadrant_camera(camera, i, j),
                "light": np.zeros(3, dtype=np.float32),
            }
            layer = rasterize(layer_scene(view, clear))
            rows, columns = (slice(FILL_SIDE * k, FILL_SIDE * (k + 1)) for k in (j, i))
            hit = layer["tri"] >= 0
            m = materials["material"][np.maximum(layer["tri"], 0)]
            depth[rows, columns] = np.where(hit, layer["depth"], NO_GLASS)
            shadow[rows, columns] = np.where(hit[:, :, None], through[m], F(1))
    return {"depth": depth, "shadow": shadow}


def sun_through(lights, glass_map, points, normals):
    """The sun's share (n, 3) through the glass nearest it at points (n, 3) with normals
    (n, 3) (moved one shadow texel along them): its shadow behind it, else 1, over the
    four nearest texels, bilinear (as the shadow's filter)."""
    sx, sy, w = sun_screen(
        lights["shadow_camera"], lights["shadow_texel"], points, normals
    )
    depth = glass_map["depth"]
    side = depth.shape[0]

    def through_at(ix, iy):
        inside = (ix >= 0) & (ix < side) & (iy >= 0) & (iy < side)
        ix, iy = np.clip(ix, 0, side - 1), np.clip(iy, 0, side - 1)
        stored = depth[iy, ix]
        behind = inside & (stored > NO_GLASS) & (w < stored - lights["shadow_bias"])
        return np.where(behind[:, None], glass_map["shadow"][iy, ix], F(1))

    gx, gy = sx - F(0.5), sy - F(0.5)
    x0, y0 = np.floor(gx), np.floor(gy)
    fx, fy = (gx - x0)[:, None], (gy - y0)[:, None]
    x0, y0 = x0.astype(np.int64), y0.astype(np.int64)
    top = through_at(x0, y0) * (F(1) - fx) + through_at(x0 + 1, y0) * fx
    bottom = through_at(x0, y0 + 1) * (F(1) - fx) + through_at(x0 + 1, y0 + 1) * fx
    return top * (F(1) - fy) + bottom * fy
