"""The sun's visibility traced over its disk: the share of rays toward the disk that
leave the scene, the shadow map's casters (no transparent triangle, masked holes
passed), the edge truth the map's filters are measured against."""

import numpy as np

from prism_reference.direct.shadow_filter import disk_offsets, pixel_turn
from prism_reference.material.kinds import (
    ALBEDO,
    MASK,
    MASKED,
    OPAQUE_BYTE,
    TRANSPARENT,
)
from prism_reference.material.texture import fetch
from prism_reference.trace.batch import trace
from prism_reference.trace.tracer import TMAX
from prism_reference.trace.tree import build

F = np.float32
# Times a ray is taken on past a masked hole before it counts as blocked.
HOLE_PASSES = 8


def casters(scene, materials):
    """The scene's triangles that cast the sun's shadow (all but transparent ones):
    a scene of those and their numbers in the scene."""
    kind = materials["kind"][materials["material"]]
    keep = np.nonzero(kind != TRANSPARENT)[0]
    return {"positions": scene["positions"], "indices": scene["indices"][keep]}, keep


def caster_tree(scene, materials):
    """The box tree of the casters and their numbers in the scene."""
    part, keep = casters(scene, materials)
    return build(part), keep


def hole_at(materials, tri, u, v):
    """True where the hit (triangle tri, barycentrics u, v) is a masked material's
    hole at the texture's finest level."""
    m = materials["material"][tri]
    masked = materials["kind"][m] == MASKED
    out = np.zeros(len(tri), dtype=bool)
    if not masked.any() or len(materials["mip"]) == 0:
        return out
    rows = np.nonzero(masked)[0]
    uv = materials["uv"][tri[rows]]
    a, b = u[rows, None], v[rows, None]
    at = (uv[:, 0] * (F(1) - a - b) + uv[:, 1] * a) + uv[:, 2] * b
    textures = materials["textures"][m[rows]]
    level = np.zeros(len(rows), dtype=np.int64)
    alpha = np.full(len(rows), 255, dtype=np.int64)
    for slot in (ALBEDO, MASK):
        has = textures[:, slot] >= 0
        if has.any():
            tex = np.maximum(textures[:, slot], 0)
            texel = fetch(materials, tex, level, at[:, 0], at[:, 1])
            alpha = np.where(has, texel[:, 3], alpha)
    out[rows] = alpha < OPAQUE_BYTE
    return out


def blocked(tree, keep, materials, origin, direction):
    """True where the ray hits a caster that is not a masked hole."""
    hit = np.zeros(len(origin), dtype=bool)
    live = np.arange(len(origin))
    o = origin.astype(np.float32)
    for _ in range(HOLE_PASSES):
        t, tri, u, v = trace(tree, o[live], direction[live], TMAX)
        found = tri >= 0
        live, t, tri, u, v = live[found], t[found], tri[found], u[found], v[found]
        if not len(live):
            return hit
        hole = hole_at(materials, keep[tri], u, v)
        hit[live[~hole]] = True
        live, t = live[hole], t[hole]
        step = np.maximum(t, F(0)) * F(1.0001) + F(1e-6)
        o[live] = o[live] + direction[live] * step[:, None]
    hit[live] = True
    return hit


def sun_disk(sun, angle, rays, turn):
    """Unit directions (n, rays, 3) spread evenly over the sun's disk of diameter
    `angle` (radians) about `sun`, the spiral turned by turn (n,)."""
    s = np.asarray(sun, np.float64)
    s = s / np.linalg.norm(s)
    helper = np.array([0.0, 1.0, 0.0]) if abs(s[1]) < 0.99 else np.array([1.0, 0, 0])
    a = np.cross(helper, s)
    a /= np.linalg.norm(a)
    b = np.cross(s, a)
    disk = disk_offsets(rays, turn).astype(np.float64) * np.tan(angle / 2)
    d = s + disk[..., 0:1] * a + disk[..., 1:2] * b
    return (d / np.linalg.norm(d, axis=-1, keepdims=True)).astype(np.float32)


def traced_sun(tree, keep, materials, points, normals, sun, angle, rays, eps, pixels):
    """The share (n,) of `rays` rays from points moved eps along their normals toward
    the sun's disk that leave the scene; pixels (n, 2) turn each point's spiral."""
    turn = pixel_turn(pixels[:, 0], pixels[:, 1])
    d = sun_disk(sun, angle, rays, turn).reshape(-1, 3)
    o = np.repeat(points + normals * F(eps), rays, axis=0)
    hit = blocked(tree, keep, materials, o, d).reshape(-1, rays)
    return F(1) - hit.sum(1).astype(np.float32) / F(rays)
