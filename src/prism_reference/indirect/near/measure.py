"""The cosine measure of a pixel's hemisphere along one screen slice: the slice's frame,
the closed-form distribution over its angle from the view vector, and its 32 equal bits.
"""

import numpy as np

BITS = 32
HALF = np.pi / 2
# arctan(z) / z on [0, 1] as a polynomial in z^2 (largest error 2.5e-7)
ATAN = (
    0.999996112,
    -0.333173680,
    0.198078150,
    -0.132333397,
    0.079623626,
    -0.033604179,
    0.006811779,
)


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


def atan_unit(z):
    """arctan(z) (n,) for z in [0, 1] by an odd polynomial of degree 13."""
    z2 = z * z
    out = np.full_like(z, ATAN[-1])
    for c in ATAN[-2::-1]:
        out = out * z2 + c
    return out * z


def side_share_free(x, y, g, total):
    """`side_share` of the angle of (x, y) (x along V, y along the side's Dp) clipped to
    [0, pi], with no trigonometric call: arctan by `atan_unit`, cos(2t - g) from x, y.
    """
    lo, hi = side_bounds(g)
    below = y < 0
    x, y = np.where(below, 1.0, x), np.where(below, 0.0, y)
    ax = np.abs(x)
    big, small = np.maximum(ax, y), np.minimum(ax, y)
    t = atan_unit(small / np.maximum(big, 1e-300))
    t = np.where(y > ax, HALF - t, t)
    t = np.where(x < 0, np.pi - t, t)
    r2 = np.maximum(x * x + y * y, 1e-300)
    cos2, sin2 = (x * x - y * y) / r2, 2 * x * y / r2
    c = -(cos2 * np.cos(g) + sin2 * np.sin(g)) / 4 + t * np.sin(g) / 2
    share = (c - primitive(lo, g)) / np.maximum(total, 1e-30)
    share = np.where(t <= lo, 0.0, np.where(t >= hi, 1.0, share))
    return np.clip(share, 0.0, 1.0)


def bit_range(u0, u1):
    """The mask (n,) uint32 of the bits from floor(BITS u0) up to ceil(BITS u1) - 1."""
    b0 = np.clip(np.floor(u0 * BITS), 0, BITS).astype(np.uint64)
    b1 = np.clip(np.ceil(u1 * BITS), 0, BITS).astype(np.uint64)
    one = np.uint64(1)
    upper = (one << b1) - one
    lower = (one << b0) - one
    return (upper & ~lower).astype(np.uint32)
