"""Generated scenes: spheres of mixed size over a ground, one camera, one light, equal on
every host; and the per-index hash all random numbers come from."""

import numpy as np

from prism_reference.scene.camera import cross, normalize
from prism_reference.scene.frame import HEIGHT, WIDTH

GOLDEN = np.uint32(0x9E3779B1)
SCALE = np.float32(1.0 / 16777216.0)
# Names of the scenes and the triangle count aimed at.
PRESETS = {"tiny": 300, "s10k": 10_000, "s100k": 100_000, "s1m": 1_000_000}
TINY_SPHERES = 5
TAN_HALF_FOV = 0.55


def hash32(index, stream=0, seed=0):
    """A 32-bit hash of (index, stream, seed); index may be an array of integers."""
    with np.errstate(over="ignore"):
        h = np.asarray(index).astype(np.uint32) * GOLDEN
        h = h + np.uint32(((stream + 1) * 0x85EBCA6B) & 0xFFFFFFFF)
        h = h + np.uint32(seed & 0xFFFFFFFF)
        h = h ^ (h >> np.uint32(16))
        h = h * np.uint32(0x7FEB352D)
        h = h ^ (h >> np.uint32(15))
        h = h * np.uint32(0x846CA68B)
        return h ^ (h >> np.uint32(16))


def uniform(index, stream=0, seed=0):
    """Uniform float32 in [0, 1) with 24 random bits, from `hash32`."""
    h = hash32(index, stream, seed)
    return (h >> np.uint32(8)).astype(np.float32) * SCALE


def f64(x):
    """Float64 copy of an array or scalar."""
    return np.asarray(x, dtype=np.float64)


def draw(index, stream, seed):
    """Float64 uniform numbers in [0, 1) from the hash, one per index."""
    return f64(uniform(index, stream, seed))


def cube_sphere(n):
    """Unit sphere from a cube with n x n quads per face: (6(n+1)^2, 3), (12n^2, 3)."""
    s = np.linspace(-1.0, 1.0, n + 1)
    a, b = np.meshgrid(s, s, indexing="ij")
    one = np.ones_like(a)
    faces = [(one, a, b), (-one, a, b), (a, one, b), (a, -one, b), (a, b, one)]
    faces.append((a, b, -one))
    verts, tris = [], []
    for f, (x, y, z) in enumerate(faces):
        p = np.stack([x, y, z], axis=-1).reshape(-1, 3)
        verts.append(p / np.sqrt((p * p).sum(axis=1, keepdims=True)))
        i, j = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
        v00 = (i * (n + 1) + j).ravel() + f * (n + 1) ** 2
        v10, v01, v11 = v00 + (n + 1), v00 + 1, v00 + n + 2
        tris.append(np.stack([v00, v10, v01], axis=1))
        tris.append(np.stack([v10, v11, v01], axis=1))
    return np.concatenate(verts), np.concatenate(tris)


def ground_grid(cells, half):
    """A flat cells x cells grid on y = 0: vertices, triangles, tint in [0, 1]."""
    s = np.linspace(-half, half, cells + 1)
    x, z = np.meshgrid(s, s, indexing="ij")
    verts = np.stack([x, np.zeros_like(x), z], axis=-1).reshape(-1, 3)
    i, j = np.meshgrid(np.arange(cells), np.arange(cells), indexing="ij")
    v00 = (i * (cells + 1) + j).ravel()
    v10, v01, v11 = v00 + (cells + 1), v00 + 1, v00 + cells + 2
    tris = np.concatenate(
        [np.stack([v00, v10, v01], axis=1), np.stack([v10, v11, v01], axis=1)]
    )
    ramp_x = np.abs(np.arange(len(verts)) // (cells + 1) % 8 - 4) / 4
    ramp_z = np.abs(np.arange(len(verts)) % (cells + 1) % 8 - 4) / 4
    return verts, tris, 0.5 * (ramp_x + ramp_z)


def sphere_params(count, half, seed):
    """Centres, radii and base colours of `count` spheres; the first three are big."""
    k = np.arange(count)
    u = [draw(k, stream, seed) for stream in range(7)]
    radius = half * (0.008 + 0.1 * (u[0] * u[0] * u[0]) ** 2)
    centre = np.stack(
        [
            half * 0.9 * (2 * u[1] - 1),
            radius * (1 + 2 * u[2] * u[2]),
            half * 0.9 * (2 * u[3] - 1),
        ],
        axis=1,
    )
    base = np.stack([0.25 + 0.7 * u[4], 0.25 + 0.7 * u[5], 0.25 + 0.7 * u[6]], axis=1)
    near = [(-0.25, -0.78, 0.12), (0.2, -0.85, 0.09), (0.02, -0.55, 0.07)]
    for i, (x, z, r) in enumerate(near[: min(3, count)]):
        radius[i] = half * r
        centre[i] = [half * x, half * r, half * z]
    return centre, radius, base


def build_arrays(n_triangles, spheres, seed):
    """Positions, colours and indices (float64 / int64) of the scene."""
    half = 30.0 * np.sqrt(n_triangles / 1e4)
    cells = max(2, int(np.floor(np.sqrt(0.3 * n_triangles / 2) + 0.5)))
    centre, radius, base = sphere_params(spheres, half, seed)
    share = radius * radius / (radius * radius).sum()
    handlers = np.maximum(2, np.floor(np.sqrt(0.7 * n_triangles * share / 12) + 0.5))
    gv, gt, tint = ground_grid(cells, 1.5 * half)
    p = tint[:, None]
    gc = np.hstack([0.30 + 0.15 * p, 0.38 + 0.12 * p, 0.25 + 0.05 * p])
    pos, col, idx, offset = [gv], [gc], [gt], len(gv)
    for s in range(spheres):
        unit, tris = cube_sphere(int(handlers[s]))
        pos.append(centre[s] + radius[s] * unit)
        shade = 0.6 + 0.4 * (0.5 + 0.5 * unit[:, 1:2])
        col.append(base[s] * shade)
        idx.append(tris + offset)
        offset += len(unit)
    return half, np.concatenate(pos), np.concatenate(col), np.concatenate(idx)


def make_camera(half):
    """Camera arrays: looks from behind the scene's near edge toward its centre."""
    eye = np.array([0.0, 0.25 * half, -1.3 * half])
    fwd = normalize(np.array([0.0, -0.1 * half, 0.3 * half]) - eye)
    right = normalize(cross(fwd, np.array([0.0, 1.0, 0.0])))
    up = cross(right, fwd)
    focal = (WIDTH / 2) / TAN_HALF_FOV
    camera = np.concatenate([eye, right, up, fwd, [focal, WIDTH / 2, HEIGHT / 2, 0.05]])
    return camera.astype(np.float32)


def make_scene(n_triangles, spheres=None, seed=1):
    """The scene dict for about n_triangles triangles."""
    if spheres is None:
        spheres = max(4, int(np.floor(60 * np.sqrt(n_triangles / 1e4) + 0.5)))
    half, pos, col, idx = build_arrays(n_triangles, spheres, seed)
    cells = max(2, int(np.floor(np.sqrt(0.3 * n_triangles / 2) + 0.5)))
    light = np.array([-0.6 * half, 1.2 * half, -0.8 * half], dtype=np.float32)
    meta = np.array([len(idx), len(pos), spheres, cells, seed], dtype=np.int32)
    return {
        "positions": pos.astype(np.float32),
        "colors": col.astype(np.float32),
        "indices": idx.astype(np.int32),
        "camera": make_camera(half),
        "light": light,
        "eps": np.array([1e-4 * half], dtype=np.float32),
        "meta": meta,
    }


def make_preset(name):
    """One of the PRESETS by name."""
    spheres = TINY_SPHERES if name == "tiny" else None
    return make_scene(PRESETS[name], spheres=spheres)
