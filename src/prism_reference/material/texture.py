"""Texture sampling: a texel's byte as a value, the mip level of a triangle, the nearest
texel of a level."""

import numpy as np

F = np.float32
# Texel byte to value: albedo as linear colour, the others to [0, 1], normals to [-1, 1].
TEXEL_LINEAR = ((np.arange(256) / 255.0) ** 2.2).astype(np.float32)
TEXEL_UNIT = (np.arange(256) / 255.0).astype(np.float32)
TEXEL_SIGNED = (np.arange(256) * 2.0 / 255.0 - 1.0).astype(np.float32)


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
