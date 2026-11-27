"""The cosine measure of a pixel's hemisphere along one screen slice: the slice's frame,
the closed-form distribution over its angle from the view vector, and its 32 equal bits.
"""

import numpy as np

BITS = 32
HALF = np.pi / 2


def slice_frame(point, normal, screen_dir):
    """For camera-space points and normals (n, 3) and screen directions (n, 2) (x right,
    y down): V (n, 3) toward the eye, Dp (n, 3) the unit slice direction orthogonal to V,
    the projected normal's length (n,) and its angle g (n,) from V toward Dp."""
    v = -point / np.linalg.norm(point, axis=1, keepdims=True)
    d = np.stack([screen_dir[:, 0], -screen_dir[:, 1], np.zeros(len(point))], 1)
    d = d - (d * v).sum(1, keepdims=True) * v
    d = d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-30)
    axis = np.cross(v, d)
    n_p = normal - (normal * axis).sum(1, keepdims=True) * axis
    length = np.linalg.norm(n_p, axis=1)
    g = np.arctan2((n_p * d).sum(1), (n_p * v).sum(1))
    return v, d, length, g


def side_bounds(g):
    """The open range [lo, hi] (n,) each of a side's angle t in [0, pi] whose directions
    lie above the projected normal's horizon (g the side's normal angle)."""
    return np.maximum(0.0, g - HALF), np.minimum(np.pi, g + HALF)


def primitive(t, g):
    """The integral of sin(u) cos(u - g) from 0 to t, up to a constant."""
    return -np.cos(2 * t - g) / 4 + t * np.sin(g) / 2


def side_total(g):
    """A side's measure (n,): the integral of |sin t| cos(t - g)^+ over t in [0, pi]."""
    lo, hi = side_bounds(g)
    return np.maximum(primitive(hi, g) - primitive(lo, g), 0.0)


def side_share(t, g, total):
    """The share (n,) in [0, 1] of a side's measure at angles below t (n,)."""
    lo, hi = side_bounds(g)
    c = primitive(np.clip(t, lo, hi), g) - primitive(lo, g)
    return np.clip(c / np.maximum(total, 1e-30), 0.0, 1.0)


def bit_range(u0, u1):
    """The mask (n,) uint32 of the bits from floor(BITS u0) up to ceil(BITS u1) - 1."""
    b0 = np.clip(np.floor(u0 * BITS), 0, BITS).astype(np.uint64)
    b1 = np.clip(np.ceil(u1 * BITS), 0, BITS).astype(np.uint64)
    one = np.uint64(1)
    upper = (one << b1) - one
    lower = (one << b0) - one
    return (upper & ~lower).astype(np.uint32)
