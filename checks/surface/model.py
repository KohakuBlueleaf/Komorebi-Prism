"""The cases of the metallic-roughness model and of the tangents."""

import numpy as np

from checks.surface.record import at_most, same
from prism_reference.material.brdf import brdf, d_ggx, diffuse, f0
from prism_reference.material.tangents import tangents

ROUGHNESS = (0.1, 0.2, 0.3, 0.5, 0.7, 1.0)
D_ROUGHNESS = (0.2, 0.3, 0.5, 0.7, 1.0)
OFF_NORMAL_DEGREES = (30, 60, 80)  # views reported, not judged
QUAD = np.array([[-1, -1, 0], [1, -1, 0], [1, 1, 0], [-1, 1, 0]], np.float64)
QUAD_INDICES = np.array([[0, 1, 2], [0, 2, 3]])
# glTF's uv of the quad: u right, v down (the image's top at the quad's top).
QUAD_UV = np.array([[0, 1], [1, 1], [1, 0], [0, 0]], np.float64)


def hemisphere(count, rng):
    """Unit vectors (count, 3) with z > 0."""
    v = rng.normal(size=(count, 3))
    v[:, 2] = np.abs(v[:, 2]) + 1e-3
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def furnace(metallic, roughness, view_degrees):
    """The cosine-weighted integral of the brdf (base 1) over the hemisphere, 64 x 256
    points, for a view at `view_degrees` from the normal."""
    u = (np.arange(64) + 0.5) / 64
    phi = (np.arange(256) + 0.5) / 256 * 2 * np.pi
    uu, pp = np.meshgrid(u, phi, indexing="ij")
    s, c = np.sqrt(uu), np.sqrt(1 - uu)
    l = np.stack([s * np.cos(pp), s * np.sin(pp), c], axis=-1)
    t = np.radians(view_degrees)
    v = np.array([np.sin(t), 0.0, np.cos(t)])
    f = brdf(np.ones(3), metallic, roughness, np.array([0.0, 0.0, 1.0]), v, l)
    return np.pi * f[..., 0].mean()


def d_integral(roughness, steps=4096):
    """The integral of D (n.h) over the hemisphere of half vectors."""
    theta = (np.arange(steps) + 0.5) / steps * np.pi / 2
    c = np.cos(theta)
    integrand = d_ggx(c, roughness**2) * c * np.sin(theta)
    return integrand.sum() * (np.pi / 2 / steps) * 2 * np.pi


def brdf_cases():
    """Reciprocity, the white furnace, D's integral, f0 and diffuse at their ends; the
    furnace at views off the normal, returned."""
    rng = np.random.default_rng(7)
    count = 4096
    n = np.tile([0.0, 0.0, 1.0], (count, 1))
    v, l = hemisphere(count, rng), hemisphere(count, rng)
    base = rng.uniform(size=(count, 3))
    metallic, roughness = rng.uniform(size=count), rng.uniform(0.05, 1, size=count)
    forward = brdf(base, metallic, roughness, n, v, l)
    backward = brdf(base, metallic, roughness, n, l, v)
    scale = np.maximum(1.0, np.abs(forward))
    same(
        "brdf reciprocity", (forward - backward) / scale, np.zeros_like(forward), 1e-12
    )
    off = {}
    for m in (0.0, 1.0):
        for r in ROUGHNESS:
            at_most(f"furnace metallic {m} roughness {r}", furnace(m, r, 0), 1 + 1e-3)
            off[f"{m} {r}"] = [round(furnace(m, r, d), 4) for d in OFF_NORMAL_DEGREES]
    for r in D_ROUGHNESS:
        same(f"D integral roughness {r}", d_integral(r), 1.0, 1e-3)
    colour = np.array([0.2, 0.5, 0.9])
    same("f0 metallic 0", f0(colour, 0.0), [0.04] * 3, 1e-12)
    same("f0 metallic 1", f0(colour, 1.0), colour, 1e-12)
    same("diffuse metallic 0", diffuse(colour, 0.0), colour / np.pi, 1e-12)
    same("diffuse metallic 1", diffuse(colour, 1.0), [0.0] * 3, 1e-12)
    return {"views_degrees": list(OFF_NORMAL_DEGREES), "values": off}


def tangent_cases():
    """A quad with glTF's plain uv: tangent +x, w +1; its u mirrored: tangent -x, w -1."""
    normals = np.tile([0.0, 0.0, 1.0], (4, 1))
    got = tangents(QUAD, normals, QUAD_UV, QUAD_INDICES)
    same("tangents plain uv", got, np.tile([1.0, 0, 0, 1], (4, 1)), 1e-6)
    mirrored = QUAD_UV * [-1, 1] + [1, 0]
    got = tangents(QUAD, normals, mirrored, QUAD_INDICES)
    same("tangents mirrored uv", got, np.tile([-1.0, 0, 0, -1], (4, 1)), 1e-6)
    got = tangents(QUAD, None, QUAD_UV, QUAD_INDICES)
    same("tangents without normals", got, np.tile([1.0, 0, 0, 1], (4, 1)), 1e-6)
