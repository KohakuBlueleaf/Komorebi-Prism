"""LIGHT's tangent frame from a record's planes in float32, as the card's scalar code
computes it, and the angle figures that compare frames."""

import numpy as np

from prism.stages.direct.light.model.numbers import F32, RSQRT_MAGIC
from prism_reference.raster.vector import cross3, dot3


def rsqrt(x):
    """1 / sqrt(x) (float32, x > 0) as the card's scalar code: the magic estimate and
    three Newton steps of multiplies and adds."""
    x = np.asarray(x, dtype=F32)
    y = (np.uint32(RSQRT_MAGIC) - (x.view(np.uint32) >> np.uint32(1))).view(F32)
    half = x * F32(0.5)
    for _ in range(3):
        y = y * (F32(1.5) - half * y * y)
    return y


def unit(v):
    """v (..., 3) over its length by rsqrt; zero where the length is zero."""
    length2 = dot3(v, v)
    safe = np.where(length2 > 0, length2, F32(1))
    return np.where((length2 > 0)[..., None], v * rsqrt(safe)[..., None], F32(0))


def to_world(cam, v):
    """Camera-space directions (n, 3) to scene space: right x + up y + forward z."""
    return (cam[3:6] * v[:, 0:1] + cam[6:9] * v[:, 1:2]) + cam[9:12] * v[:, 2:3]


def frame_from_planes(cam, w_plane, u_plane, v_plane):
    """The tangent frame (n, 3, 3: tangent, bitangent, eye-facing normal) and validity
    from each record's planes of 1/z, u/z, v/z (n, 3), float32; not valid where det M
    or the tangent is 0."""
    f, cx, cy = cam[12], cam[13], cam[14]

    def centred(plane):
        p = plane.astype(F32)
        return np.stack([p[:, 0], p[:, 1], (p[:, 0] * cx + p[:, 1] * cy) + p[:, 2]], 1)

    m0, m1, m2 = centred(w_plane), centred(u_plane), centred(v_plane)
    normal = -np.stack([m0[:, 0] * f, -(m0[:, 1] * f), m0[:, 2]], 1)
    normal = unit(to_world(cam, normal))
    det = dot3(m0, cross3(m1, m2))
    sign = np.where(det < 0, F32(-1), F32(1))[:, None]
    scale = np.array([1, -1, f], dtype=F32)
    along_u = to_world(cam, cross3(m2, m0) * scale) * sign
    along_v = to_world(cam, cross3(m0, m1) * scale) * sign
    tangent = along_u - normal * dot3(normal, along_u)[:, None]
    tangent = unit(tangent)
    side = cross3(normal, tangent)
    side = np.where((dot3(side, along_v) < 0)[:, None], -side, side)
    valid = (det != 0) & (dot3(tangent, tangent) > 0)
    return np.stack([tangent, side, normal], axis=1), valid


def angle_degrees(a, b):
    """Angles (n,) in degrees between unit vectors a and b (float64)."""
    cosine = np.clip(
        (a.astype(np.float64) * b.astype(np.float64)).sum(axis=-1), -1.0, 1.0
    )
    return np.degrees(np.arccos(cosine))


def figures(values):
    """Median, 99th percentile and largest of angles (degrees), and the count."""
    if len(values) == 0:
        return {"n": 0}
    return {
        "n": len(values),
        "median": round(float(np.median(values)), 5),
        "p99": round(float(np.percentile(values, 99)), 5),
        "max": round(float(np.max(values)), 5),
        "over_2deg": int((values > 2).sum()),
    }
