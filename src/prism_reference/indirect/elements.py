"""Surface elements: sampled by area over the triangles, probed for the void, padded to
whole units."""

import numpy as np

from prism_reference.material.kinds import ALBEDO, EMISSIVE, TRANSPARENT
from prism_reference.material.texture import TEXEL_LINEAR, fetch
from prism_reference.raster.vector import cross3, normalized
from prism_reference.scene.generated import uniform
from prism_reference.trace.batch import trace
from prism_reference.trace.tracer import TMAX

F = np.float32
# The default count, the sampling seed, and the probe (rays, seed, dead share, near
# distance in eps) that drops elements seeing only the void or buried.
ELEMENTS = 50_000
SAMPLE_SEED = 31
PROBE_RAYS, PROBE_SEED, PROBE_DEAD, PROBE_NEAR = 32, 41, 0.97, 10.0


def triangle_geometry(mesh):
    """Corners (T, 3, 3), areas (T,) and unit normals (T, 3) by the winding, float64."""
    p = mesh["positions"][mesh["indices"]].astype(np.float64)
    c = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    area = 0.5 * np.linalg.norm(c, axis=1)
    return p, area, c / np.maximum(2 * area, 1e-30)[:, None]


def triangle_colour(materials, coarse=4):
    """Per triangle a linear colour (T, 3): the albedo texture at the centroid's (u, v)
    in the level `coarse` above the last times the base colour; else the base."""
    m = materials["material"]
    tex = materials["textures"][m, ALBEDO]
    base = materials["base_colour"][m]
    out = base.astype(F).copy()
    has = tex >= 0
    if has.any() and len(materials["mip"]):
        tx = tex[has]
        level = np.maximum(materials["levels"][tx] - 1 - coarse, 0)
        uv = materials["uv"][has].mean(1).astype(F)
        texel = fetch(materials, tx, level, uv[:, 0], uv[:, 1])
        out[has] = TEXEL_LINEAR[texel[:, :3]] * base[has]
    return out


def cosine_directions(index, normal, seed):
    """Cosine-weighted unit directions (n, 3) float32 about normals (n, 3), one per hash
    index (n,), in the frame of `visibility.bake_directions`."""
    u1 = uniform(index, 0, seed)
    u2 = uniform(index, 1, seed)
    r, phi = np.sqrt(u1), F(2 * np.pi) * u2
    normal = normal.astype(F)
    helper = np.where(
        (np.abs(normal[:, 0]) < F(0.9))[:, None], F([1, 0, 0]), F([0, 1, 0])
    )
    t = normalized(cross3(helper, normal))
    b = cross3(normal, t)
    up = np.sqrt(np.maximum(F(1) - u1, F(0)))
    return (t * (r * np.cos(phi))[:, None] + b * (r * np.sin(phi))[:, None]) + (
        normal * up[:, None]
    )


def sample_elements(mesh, materials, count):
    """`count` points by area (glass has none), uniform in their triangle from the hash
    of k: position, normal, area A / count, albedo, emission; and the spacing."""
    p, area, normal = triangle_geometry(mesh)
    kind = materials["kind"][materials["material"]]
    area = np.where(kind == TRANSPARENT, 0.0, area)
    cumulative = np.cumsum(area)
    total = cumulative[-1]
    k = np.arange(count)
    tri = np.minimum(
        np.searchsorted(cumulative, (k + 0.5) * (total / count)), len(area) - 1
    )
    su = np.sqrt(uniform(k, 0, SAMPLE_SEED).astype(np.float64))
    u2 = uniform(k, 1, SAMPLE_SEED).astype(np.float64)
    b0, b1 = 1 - su, su * (1 - u2)
    q = p[tri]
    pos = (
        q[:, 0] * b0[:, None] + q[:, 1] * b1[:, None] + q[:, 2] * (1 - b0 - b1)[:, None]
    )
    colour = triangle_colour(materials)[tri]
    glow = (kind[tri] == EMISSIVE)[:, None]
    elements = {
        "position": pos.astype(F),
        "normal": normal[tri].astype(F),
        "area": np.full(count, total / count, F),
        "albedo": np.where(glow, F(0), colour).astype(F),
        "emission": np.where(glow, colour, F(0)).astype(F),
        "triangle": tri.astype(np.int32),
        "sample": k.astype(np.int32),
    }
    return elements, float(np.sqrt(total / count))


def probe(tree, elements, eps):
    """Per element the shares of PROBE_RAYS cosine rays from p + eps n that escape and
    that hit within PROBE_NEAR eps; dead when the two add up to more than PROBE_DEAD."""
    p, n = elements["position"], elements["normal"]
    escape, near = np.zeros(len(p)), np.zeros(len(p))
    index = elements["sample"].astype(np.int64) * PROBE_RAYS
    for k in range(PROBE_RAYS):
        d = cosine_directions(index + k, n, PROBE_SEED)
        t, tri, _, _ = trace(tree, p + n * F(eps), d, TMAX)
        escape += tri < 0
        near += (tri >= 0) & (t < F(PROBE_NEAR * eps))
    return escape / PROBE_RAYS, near / PROBE_RAYS


def subset(elements, keep):
    """The elements at the indices or mask `keep`."""
    return {k: v[keep] for k, v in elements.items()}


def padded(elements, count):
    """The elements and zero-area copies of the first up to `count` (a multiple of
    UNIT), and which are real."""
    extra = count - len(elements["position"])
    out = {
        k: np.concatenate([v, np.repeat(v[:1], extra, 0)]) for k, v in elements.items()
    }
    out["area"][-extra or len(out["area"]) :] = 0
    out["sample"][-extra or len(out["sample"]) :] = -1
    return out, np.arange(count) < count - extra
