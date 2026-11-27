"""The sun's shadow: its camera, the shadow map (in quadrants of FILL's frame) and the
filtered lookup a point makes."""

import numpy as np

from prism_reference.raster.frames import rasterize, rasterize_shaded
from prism_reference.raster.setup import to_screen
from prism_reference.scene.frame import WIDTH

F = np.float32
# The map's default side, FILL's frame (a larger side is rendered in quadrants of it),
# the sun camera's distance in scene radii.
SHADOW_SIDE = 2048
FILL_SIDE = WIDTH
SUN_DISTANCE = 1000.0


def sun_camera(positions, sun, side=SHADOW_SIDE, radii=SUN_DISTANCE):
    """A camera (16,) float32 `radii` scene radii along the sun's direction looking at
    the scene box's centre, its side x side frame covering the box (right = y x fwd)."""
    lo, hi = positions.min(0).astype(np.float64), positions.max(0).astype(np.float64)
    centre, radius = (lo + hi) / 2, np.linalg.norm(hi - lo) / 2
    distance = radii * radius
    fwd = -np.asarray(sun, np.float64)
    helper = np.array([0.0, 1.0, 0.0]) if abs(fwd[1]) < 0.99 else np.array([1, 0, 0])
    right = np.cross(helper, fwd)
    right /= np.linalg.norm(right)
    up = np.cross(fwd, right)
    box = np.stack(np.meshgrid(*zip(lo, hi), indexing="ij"), -1).reshape(-1, 3)
    half = np.abs(np.stack([(box - centre) @ right, (box - centre) @ up])).max()
    focal = (side / 2) * (distance - radius) / half
    eye = centre - fwd * distance
    tail = [focal, side / 2, side / 2, distance - 2 * radius]
    return np.concatenate([eye, right, up, fwd, tail]).astype(np.float32)


def quadrant_camera(camera, i, j):
    """The camera (16,) float32 of quadrant (i, j) of a view `camera` whose side is a
    multiple of FILL_SIDE: its pixel (x, y) is the view's (x + FILL_SIDE i, y + ...j).
    """
    out = np.array(camera, dtype=np.float32)
    out[13] = out[13] - F(FILL_SIDE * i)
    out[14] = out[14] - F(FILL_SIDE * j)
    return out


def sun_view(scene, sun, side=SHADOW_SIDE, radii=SUN_DISTANCE):
    """The shadow map's camera (sun_camera) and a shadow texel's world size at the
    scene's centre, without the map."""
    camera = sun_camera(scene["positions"], sun, side, radii)
    distance = np.linalg.norm(
        camera[0:3].astype(np.float64)
        - (scene["positions"].min(0) + scene["positions"].max(0)) / 2
    )
    return camera, F(distance / camera[12])


def shadow_map(scene, sun, materials=None, side=SHADOW_SIDE, radii=SUN_DISTANCE):
    """The 1/z (side, side) of the scene from the sun's camera, the camera and a shadow
    texel's world size at the scene's centre; with materials `rasterize_shaded`'s 1/z.
    """
    if side % FILL_SIDE:
        raise ValueError(f"a shadow map's side {side} is not a multiple of {FILL_SIDE}")
    camera, texel = sun_view(scene, sun, side, radii)
    return map_at(scene, camera, materials, side), camera, texel


def map_at(scene, camera, materials=None, side=SHADOW_SIDE):
    """The 1/z (side, side) of the scene from a sun `camera` of that side, rendered in
    quadrants of FILL's frame; with materials `rasterize_shaded`'s 1/z."""
    if side % FILL_SIDE:
        raise ValueError(f"a shadow map's side {side} is not a multiple of {FILL_SIDE}")
    depth = np.empty((side, side), dtype=np.float32)
    for j in range(side // FILL_SIDE):
        for i in range(side // FILL_SIDE):
            view = {
                "positions": scene["positions"],
                "indices": scene["indices"],
                "colors": np.zeros((len(scene["positions"]), 3), dtype=np.float32),
                "camera": quadrant_camera(camera, i, j),
                "light": np.zeros(3, dtype=np.float32),
            }
            if materials is None:
                part = rasterize(view)["depth"]
            else:
                part = rasterize_shaded(view, materials)["depth"]
            rows, columns = (slice(FILL_SIDE * k, FILL_SIDE * (k + 1)) for k in (j, i))
            depth[rows, columns] = part
    return depth


def sun_screen(cam, texel, points, normals):
    """Map x, y and 1/z (n,) in a sun camera of points (n, 3) moved one shadow texel
    (`texel`, its world size) along their normals (n, 3)."""
    d = (points + normals * texel) - cam[0:3]
    xc = (d[:, 0] * cam[3] + d[:, 1] * cam[4]) + d[:, 2] * cam[5]
    yc = (d[:, 0] * cam[6] + d[:, 1] * cam[7]) + d[:, 2] * cam[8]
    zc = (d[:, 0] * cam[9] + d[:, 1] * cam[10]) + d[:, 2] * cam[11]
    return to_screen(cam, xc, yc, zc)


def sun_shadow(lights, points, normals, pcf=True):
    """Sun light (n,) float32 in [0, 1] at points (n, 3) with normals (n, 3), each moved
    one shadow texel along its normal; pcf: four texels, bilinear; else the nearest."""
    depth = lights["shadow_map"]
    sx, sy, w = sun_screen(
        lights["shadow_camera"], lights["shadow_texel"], points, normals
    )
    side = depth.shape[0]

    def lit_at(ix, iy):
        inside = (ix >= 0) & (ix < side) & (iy >= 0) & (iy < side)
        stored = depth[np.clip(iy, 0, side - 1), np.clip(ix, 0, side - 1)]
        return np.where(inside & (w < stored - lights["shadow_bias"]), F(0), F(1))

    if not pcf:
        return lit_at(np.floor(sx).astype(np.int64), np.floor(sy).astype(np.int64))
    gx, gy = sx - F(0.5), sy - F(0.5)
    x0, y0 = np.floor(gx), np.floor(gy)
    fx, fy = gx - x0, gy - y0
    x0, y0 = x0.astype(np.int64), y0.astype(np.int64)
    top = lit_at(x0, y0) * (F(1) - fx) + lit_at(x0 + 1, y0) * fx
    bottom = lit_at(x0, y0 + 1) * (F(1) - fx) + lit_at(x0 + 1, y0 + 1) * fx
    return top * (F(1) - fy) + bottom * fy
