"""Vertex tangents of a primitive without TANGENT: per triangle from the uv derivatives,
summed per vertex by corner angle, made orthogonal to the normal, w the handedness."""

import numpy as np


def unit_rows(v):
    """Rows of `v` scaled to length 1 (rows of length 0 stay 0)."""
    length = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.where(length > 0, length, 1.0)


def any_perpendicular(n):
    """A unit vector perpendicular to each unit row of n."""
    pick = np.where((np.abs(n[:, 0]) < 0.9)[:, None], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0])
    return unit_rows(np.cross(n, pick))


def corner_angles(p):
    """The angle at each corner (T, 3) of triangles p (T, 3, 3)."""
    angles = np.zeros(p.shape[:2])
    for k in range(3):
        a = unit_rows(p[:, (k + 1) % 3] - p[:, k])
        b = unit_rows(p[:, (k + 2) % 3] - p[:, k])
        angles[:, k] = np.arccos(np.clip(np.sum(a * b, axis=1), -1.0, 1.0))
    return angles


def tangents(positions, normals, uv, indices):
    """(V, 4) float32 tangents: xyz along +u, w = +1 when the bitangent cross(n, t) w
    runs along -v (the image's up in the description's uv), else -1."""
    p = np.asarray(positions, dtype=np.float64)
    idx = np.asarray(indices, dtype=np.int64)
    t_uv = np.asarray(uv, dtype=np.float64)[idx]
    tri = p[idx]
    e1, e2 = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
    du1, dv1 = t_uv[:, 1, 0] - t_uv[:, 0, 0], t_uv[:, 1, 1] - t_uv[:, 0, 1]
    du2, dv2 = t_uv[:, 2, 0] - t_uv[:, 0, 0], t_uv[:, 2, 1] - t_uv[:, 0, 1]
    det = du1 * dv2 - du2 * dv1
    inv = np.where(det != 0, 1.0 / np.where(det != 0, det, 1.0), 0.0)[:, None]
    along_u = (e1 * dv2[:, None] - e2 * dv1[:, None]) * inv
    along_v = (e2 * du1[:, None] - e1 * du2[:, None]) * inv
    weight = corner_angles(tri)
    sum_u = np.zeros_like(p)
    sum_v = np.zeros_like(p)
    for k in range(3):
        np.add.at(sum_u, idx[:, k], along_u * weight[:, k, None])
        np.add.at(sum_v, idx[:, k], along_v * weight[:, k, None])
    if normals is None:
        n = np.zeros_like(p)
        face = np.cross(e1, e2)
        for k in range(3):
            np.add.at(n, idx[:, k], face * weight[:, k, None])
        n = unit_rows(n)
    else:
        n = unit_rows(np.asarray(normals, dtype=np.float64))
    t = sum_u - n * np.sum(n * sum_u, axis=1, keepdims=True)
    length = np.linalg.norm(t, axis=1)
    t = np.where((length > 0)[:, None], unit_rows(t), any_perpendicular(n))
    w = np.where(np.sum(np.cross(n, t) * -sum_v, axis=1) < 0, -1.0, 1.0)
    return np.concatenate([t, w[:, None]], axis=1).astype(np.float32)
