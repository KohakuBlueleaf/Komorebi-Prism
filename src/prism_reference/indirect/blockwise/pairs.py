"""The form factor of listed element pairs with visibility, the facing test of whole
blocks by products of rank 3, and which elements face any other."""

import numpy as np

from prism_reference.trace.batch import trace

F = np.float32
CHUNK = 1 << 22  # pairs evaluated at once


def kernel(p, n, area, i, j):
    """F without visibility (float64) of pairs (i, j): the form factor of
    `form_factors.form_factor_rows`, 0 where i == j."""
    d = p[j] - p[i]
    r2 = np.einsum("ij,ij->i", d, d)
    r = np.sqrt(np.maximum(r2, 1e-30))
    ci = np.einsum("ij,ij->i", n[i], d) / r
    cj = -np.einsum("ij,ij->i", n[j], d) / r
    den = np.pi * r2 + area[j]
    top = np.maximum(ci, 0) * np.maximum(cj, 0) * area[j]
    value = np.divide(top, den, out=np.zeros_like(top), where=den > 0)
    value[i == j] = 0
    return value


def pair_values(tree, elements, i, j, eps):
    """F (float64) of pairs (i, j) with visibility: one any-hit ray from p_i + eps n_i
    to p_j + eps n_j for each pair of positive kernel; and the rays traced."""
    p = elements["position"].astype(np.float64)
    n = elements["normal"].astype(np.float64)
    area = elements["area"].astype(np.float64)
    out = np.empty(len(i))
    rays = 0
    for s in range(0, len(i), CHUNK):
        a, b = i[s : s + CHUNK], j[s : s + CHUNK]
        value = kernel(p, n, area, a, b)
        live = np.nonzero(value > 0)[0]
        if len(live):
            o = p[a[live]] + n[a[live]] * eps
            e = p[b[live]] + n[b[live]] * eps
            _, tri, _, _ = trace(tree, o, e - o, 1.0, any_hit=True)
            value[live[tri >= 0]] = 0
            rays += len(live)
        out[s : s + len(a)] = value
    return out, rays


def facing(p, n, rows, cols):
    """(len(rows), len(cols)) bool: n_i . (p_j - p_i) > 0 and n_j . (p_i - p_j) > 0,
    the kernel's sign test, by two products of rank 3."""
    pr, nr, pc, nc = p[rows], n[rows], p[cols], n[cols]
    front = nr @ pc.T > np.einsum("ij,ij->i", nr, pr)[:, None]
    back = pr @ nc.T > np.einsum("ij,ij->i", nc, pc)[None, :]
    return front & back


def facing_any(position, normal, chunk=512):
    """Per element (N,) bool: some other element faces it (its row of F may be > 0)."""
    p, n = position.astype(np.float64), normal.astype(np.float64)
    out = np.zeros(len(p), dtype=bool)
    every = np.arange(len(p))
    for s in range(0, len(p), chunk):
        rows = every[s : s + chunk]
        out[rows] = facing(p, n, rows, every).any(1)
    return out
