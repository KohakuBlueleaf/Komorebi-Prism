"""The sky's visibility baked per vertex: the share of cosine rays from a vertex that
leave the scene."""

import concurrent.futures

import numpy as np

from prism_reference.native.loader import library
from prism_reference.raster.vector import cross3, dot3, normalized
from prism_reference.scene.generated import uniform
from prism_reference.trace.batch import trace
from prism_reference.trace.tracer import TMAX

F = np.float32
# Rays per vertex and the hash seed of their directions.
VIS_RAYS = 64
VIS_SEED = 11
VIS_CHUNK = 1 << 14  # vertices a thread bakes at once
_BAKE = {}


def vertex_normals(positions, indices):
    """Unit area-weighted normals (V, 3) float32 of the vertices (zero where the
    triangles around a vertex cancel)."""
    p = positions[indices].astype(np.float64)
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    total = np.zeros((len(positions), 3))
    for k in range(3):
        np.add.at(total, indices[:, k], n)
    length = np.linalg.norm(total, axis=1)
    return np.where(
        (length > 0)[:, None], total / np.maximum(length, 1e-300)[:, None], 0
    ).astype(np.float32)


def bake_directions(vertex, normal):
    """VIS_RAYS cosine-weighted unit directions (n, VIS_RAYS, 3) about the normals
    (n, 3), from the hash of vertex * VIS_RAYS + ray."""
    index = vertex[:, None].astype(np.int64) * VIS_RAYS + np.arange(VIS_RAYS)
    u1 = uniform(index, 0, VIS_SEED)
    u2 = uniform(index, 1, VIS_SEED)
    r, phi = np.sqrt(u1), F(2 * np.pi) * u2
    helper = np.where(
        (np.abs(normal[:, 0]) < F(0.9))[:, None], F([1, 0, 0]), F([0, 1, 0])
    )
    t = normalized(cross3(helper, normal))
    b = cross3(normal, t)
    up = np.sqrt(np.maximum(F(1) - u1, F(0)))
    return (
        t[:, None] * (r * np.cos(phi))[..., None]
        + b[:, None] * (r * np.sin(phi))[..., None]
    ) + normal[:, None] * up[..., None]


def _bake_chunk(span):
    """Visibility of vertices start..end (the arrays in _BAKE)."""
    start, end = span
    positions, normals, tree, eps = (
        _BAKE[k] for k in ("positions", "normals", "tree", "eps")
    )
    vertex = np.arange(start, end)
    n = normals[start:end]
    d = bake_directions(vertex, n).reshape(-1, 3).astype(np.float32)
    o = np.repeat(positions[start:end] + n * eps, VIS_RAYS, axis=0)
    hit = trace(tree, o, d, TMAX, any_hit=True, count=1)[1] >= 0
    vis = F(1) - hit.reshape(-1, VIS_RAYS).sum(1).astype(np.float32) / F(VIS_RAYS)
    return np.where(dot3(n, n) > 0, vis, F(1))


def bake_visibility(positions, indices, tree, eps, workers=4):
    """Per vertex the share of VIS_RAYS cosine rays from the vertex moved eps along its
    normal that leave without a hit (1 where the normal is zero), on `workers` threads.
    """
    _BAKE.update(
        positions=positions,
        normals=vertex_normals(positions, indices),
        tree={k: np.ascontiguousarray(tree[k]) for k in ("tris", "leaf_tri")},
        eps=F(eps),
    )
    spans = [
        (s, min(s + VIS_CHUNK, len(positions)))
        for s in range(0, len(positions), VIS_CHUNK)
    ]
    if workers > 1:
        library()  # built before the threads ask for it
        with concurrent.futures.ThreadPoolExecutor(workers) as pool:
            parts = list(pool.map(_bake_chunk, spans))
    else:
        parts = [_bake_chunk(span) for span in spans]
    _BAKE.clear()
    return np.concatenate(parts).astype(np.float32)
