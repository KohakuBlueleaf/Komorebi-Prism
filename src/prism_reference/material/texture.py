"""Texture sampling: a texel's byte as a value, the mip level of a triangle, the nearest
texel of a level, a slot's uv map, a normal map's scale and its filtered length."""

import numpy as np

F = np.float32
# Texel byte to value: albedo as linear colour, the others to [0, 1], normals to [-1, 1].
TEXEL_LINEAR = ((np.arange(256) / 255.0) ** 2.2).astype(np.float32)
TEXEL_UNIT = (np.arange(256) / 255.0).astype(np.float32)
TEXEL_SIGNED = (np.arange(256) * 2.0 / 255.0 - 1.0).astype(np.float32)
NORMAL_ROUNDING = 1.0 / 128  # a unit vector in bytes: its length at least 1 - this
LEAST_LENGTH = 1e-4  # the shortest normal length read


def mip_level(texels, area2, levels):
    """The level (0 = largest) at which a texel is about a pixel: the number of
    k = 1 .. levels - 1 with texels > area2 2^(2k - 1) (doubled areas)."""
    level = np.zeros(texels.shape, dtype=np.int32)
    for k in range(1, int(levels.max(initial=1))):
        level += (texels > area2 * F(2.0 ** (2 * k - 1))) & (k < levels)
    return level


def texel_xy(materials, tex, level, u, v):
    """Column and row of the texel nearest to (u, v) in a level, coordinates wrapping,
    row 0 at v = 1; also the level's (offset, width, height)."""
    entry = materials["mip"][tex, level]
    width, height = entry[:, 1], entry[:, 2]
    s = u - np.floor(u)
    t = v - np.floor(v)
    s = np.where(np.isfinite(s), s, F(0))
    t = np.where(np.isfinite(t), t, F(0))
    x = np.minimum((s * width.astype(np.float32)).astype(np.int64), width - 1)
    y = np.minimum(
        ((F(1) - t) * height.astype(np.float32)).astype(np.int64), height - 1
    )
    return x, y, entry


def fetch(materials, tex, level, u, v):
    """The texel (n, 4) uint8 nearest to (u, v) (texel_xy)."""
    x, y, entry = texel_xy(materials, tex, level, u, v)
    start = entry[:, 0] + (y * entry[:, 1] + x) * 4
    return materials["texels"][start[:, None] + np.arange(4)]


def uv_maps(materials):
    """The materials' slot uv maps (M, 4, 2, 3); the identity when they have none."""
    found = materials.get("uv_maps")
    if found is not None:
        return np.asarray(found, F)
    return np.tile(np.eye(3, dtype=F)[:2], (len(materials["kind"]), 4, 1, 1))


def normal_scales(materials):
    """Per material (M, 3) the factor on a normal map's vector: (scale, scale, 1)."""
    scale = materials.get("normal_scale")
    if scale is None:
        return np.ones((len(materials["kind"]), 3), F)
    scale = np.asarray(scale, F)
    return np.stack([scale, scale, np.ones_like(scale)], axis=1)


def mapped_uv(maps, u, v):
    """(u, v) (n,) through per-pixel slot maps (n, 2, 3) (`uv_maps`), float32:
    (a u + b v) + c; untouched where the map is the identity."""
    u, v = np.asarray(u, F), np.asarray(v, F)
    same = np.all(maps == np.eye(3, dtype=F)[:2], axis=(1, 2))
    su = (maps[:, 0, 0] * u + maps[:, 0, 1] * v) + maps[:, 0, 2]
    sv = (maps[:, 1, 0] * u + maps[:, 1, 1] * v) + maps[:, 1, 2]
    return np.where(same, u, su), np.where(same, v, sv)


def map_area(maps):
    """|det| (n,) of slot maps' linear part (n, 2, 3): a texel area's scale, float32."""
    det = maps[:, 0, 0] * maps[:, 1, 1] - maps[:, 0, 1] * maps[:, 1, 0]
    return np.abs(det).astype(F)


def normal_length(vector):
    """The length r (n,) of looked-up normal map vectors (n, 3), within 0 .. 1: a mean
    of unit vectors, a byte's rounding (1 - NORMAL_ROUNDING) taken as 1."""
    squared = np.sum(np.asarray(vector, F) ** 2, axis=1)
    return np.minimum(np.sqrt(squared) / F(1.0 - NORMAL_ROUNDING), F(1))


def filtered_exponent(exponent, length):
    """Toksvig's Blinn-Phong exponent s' = r s / (r + s (1 - r)) (rounded, at least 1;
    0 stays 0) and the lobe's factor (1 + s') / (1 + s), by the normal's length r."""
    s = np.asarray(exponent, F)
    r = np.maximum(np.asarray(length, F), F(LEAST_LENGTH))
    wide = np.maximum(np.rint(r * s / (r + s * (F(1) - r))), F(1))
    wide = np.where(s > 0, wide, F(0))
    return wide.astype(np.int64), (F(1) + wide) / (F(1) + s)
