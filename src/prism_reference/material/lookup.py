"""Texture lookups on the card's texture data (a scene's `texels`, `mip`, `levels`): a
pixel's taps (level, column, row, weight) by mode from its uv and screen derivatives, and
the value of the taps."""

import numpy as np

from prism_reference.material.texture import TEXEL_LINEAR, mip_level, texel_xy
from prism_reference.raster.setup import at

F = np.float32
MODES = ("triangle", "nearest", "bilinear", "trilinear", "anisotropic")
MOST_TAPS = 8  # anisotropic: trilinear taps along the major axis at most
TINY = 1e-12
PAGE = 32  # a texture page: 32 x 32 texels of one level


def plane_derivatives(planes, w_plane, px, py):
    """Values (n, k), d/dx (n, k) and d/dy (n, k) at pixel centres of the values whose
    planes (n, 3, k) hold value times 1/z, with the 1/z plane (n, 3)."""
    w = at(w_plane, px, py)
    value = np.stack([at(planes[:, :, j], px, py) for j in range(planes.shape[2])], 1)
    value = value / w[:, None]
    dx = (planes[:, 0, :] - value * w_plane[:, 0:1]) / w[:, None]
    dy = (planes[:, 1, :] - value * w_plane[:, 1:2]) / w[:, None]
    return value, dx, dy


def sizes(materials, tex, level):
    """Width and height (n,) int64 of each texture's level."""
    entry = materials["mip"][tex, level]
    return entry[:, 1], entry[:, 2]


def footprint(materials, tex, d_dx, d_dy):
    """The footprint's axes in level-0 texels: major and minor lengths (n,) and the
    major axis's uv vector (n, 2), from the uv derivatives (n, 2) along x and y."""
    width, height = sizes(materials, tex, np.zeros(len(tex), np.int64))
    scale = np.stack([width, height], 1).astype(np.float64)
    dx = np.nan_to_num(np.asarray(d_dx, np.float64), nan=0.0, posinf=0.0, neginf=0.0)
    dy = np.nan_to_num(np.asarray(d_dy, np.float64), nan=0.0, posinf=0.0, neginf=0.0)
    len_x = np.linalg.norm(dx * scale, axis=1)
    len_y = np.linalg.norm(dy * scale, axis=1)
    x_major = len_x >= len_y
    major = np.where(x_major, len_x, len_y)
    minor = np.where(x_major, len_y, len_x)
    return major, minor, np.where(x_major[:, None], dx, dy)


def clamped_lod(materials, tex, lod):
    """lod (n,) clamped to 0 .. levels - 1 of each texture (not finite: 0)."""
    last = materials["levels"][tex] - 1
    lod = np.nan_to_num(np.asarray(lod, np.float64), nan=0.0, posinf=0.0, neginf=0.0)
    return np.clip(lod, 0, last)


def nearest_taps(materials, tex, level, u, v):
    """One tap (n, 1) a pixel: the texel of the level holding (u, v), coordinates
    wrapping, row 0 at v = 1 (`texture.texel_xy`)."""
    x, y, _ = texel_xy(materials, tex, level, F(u), F(v))
    return level[:, None], x[:, None], y[:, None], np.ones((len(tex), 1))


def bilinear_taps(materials, tex, level, u, v):
    """Four taps (n, 4) a pixel: the 2 x 2 texels of the level around (u, v) and their
    bilinear weights, texel centres at ((x + 0.5) / W, 1 - (y + 0.5) / H), wrapping."""
    width, height = sizes(materials, tex, level)
    fx = np.nan_to_num((u - np.floor(u)) * width - 0.5)
    fy = np.nan_to_num((1 - (v - np.floor(v))) * height - 0.5)
    x0, y0 = np.floor(fx), np.floor(fy)
    ax, ay = fx - x0, fy - y0
    x0, y0 = x0.astype(np.int64), y0.astype(np.int64)
    xs = np.stack([x0, x0 + 1, x0, x0 + 1], 1) % width[:, None]
    ys = np.stack([y0, y0, y0 + 1, y0 + 1], 1) % height[:, None]
    weight = np.stack([(1 - ax) * (1 - ay), ax * (1 - ay), (1 - ax) * ay, ax * ay], 1)
    return np.repeat(level[:, None], 4, 1), xs, ys, weight


def trilinear_taps(materials, tex, lod, u, v):
    """Eight taps (n, 8) a pixel: bilinear in levels floor(lod) and the next, weighted
    by lod's fraction (the last level twice, weights summing to 1)."""
    lod = clamped_lod(materials, tex, lod)
    low = np.floor(lod).astype(np.int64)
    high = np.minimum(low + 1, materials["levels"][tex] - 1)
    part = (lod - low)[:, None]
    a = bilinear_taps(materials, tex, low, u, v)
    b = bilinear_taps(materials, tex, high, u, v)
    return (
        np.concatenate([a[0], b[0]], 1),
        np.concatenate([a[1], b[1]], 1),
        np.concatenate([a[2], b[2]], 1),
        np.concatenate([a[3] * (1 - part), b[3] * part], 1),
    )


def anisotropic_taps(materials, tex, u, v, d_dx, d_dy, most=MOST_TAPS):
    """8 x most taps a pixel: N = ceil(major / minor') trilinear lookups (at most
    `most`) at lod log2(minor'), minor' = max(minor, major / most), spread evenly
    along the major axis; the unused taps weigh 0."""
    major, minor, axis = footprint(materials, tex, d_dx, d_dy)
    minor = np.maximum(minor, major / most)
    count = np.clip(np.ceil(major / np.maximum(minor, TINY) - 1e-9), 1, most)
    lod = np.log2(np.maximum(minor, TINY))
    parts = []
    for i in range(most):
        offset = np.where(i < count, (i + 0.5) / count - 0.5, 0.0)
        level, x, y, weight = trilinear_taps(
            materials, tex, lod, u + axis[:, 0] * offset, v + axis[:, 1] * offset
        )
        weight = np.where((i < count)[:, None], weight / count[:, None], 0.0)
        parts.append((level, x, y, weight))
    return tuple(np.concatenate([p[k] for p in parts], 1) for k in range(4))


def taps(materials, tex, u, v, d_dx, d_dy, mode, level=None, most=MOST_TAPS):
    """The taps (level, x, y, weight), each (n, K), of n pixels of textures `tex` at
    (u, v) with uv derivatives (n, 2) by `mode`: "triangle" the texel at the given
    `level` (the triangle's), "nearest" the texel at round(log2 major), "bilinear" its
    2 x 2, "trilinear" at log2 major, "anisotropic" along the major axis."""
    tex = np.asarray(tex, np.int64)
    match mode:
        case "triangle":
            return nearest_taps(materials, tex, np.asarray(level, np.int64), u, v)
        case "nearest" | "bilinear":
            major, _, _ = footprint(materials, tex, d_dx, d_dy)
            lod = clamped_lod(materials, tex, np.log2(np.maximum(major, TINY)))
            rounded = np.floor(lod + 0.5).astype(np.int64)
            pick = nearest_taps if mode == "nearest" else bilinear_taps
            return pick(materials, tex, rounded, u, v)
        case "trilinear":
            major, _, _ = footprint(materials, tex, d_dx, d_dy)
            return trilinear_taps(
                materials, tex, np.log2(np.maximum(major, TINY)), u, v
            )
        case "anisotropic":
            return anisotropic_taps(materials, tex, u, v, d_dx, d_dy, most)
    raise ValueError(f"texture lookup {mode!r}: not one of {MODES}")


def gather(materials, tex, found, table=TEXEL_LINEAR):
    """The value (n, 4) float32 of taps: rgb each texel's bytes through `table`, alpha
    the byte / 255, summed by the weights."""
    level, x, y, weight = found
    tex = np.asarray(tex, np.int64)[:, None]
    entry = materials["mip"][tex, level]
    start = entry[..., 0] + (y * entry[..., 1] + x) * 4
    texel = materials["texels"][start[..., None] + np.arange(4)]
    value = np.concatenate(
        [table[texel[..., :3]], texel[..., 3:].astype(np.float32) / F(255)], -1
    )
    return (value * weight[..., None]).sum(axis=1).astype(np.float32)


def lookup(materials, tex, u, v, d_dx, d_dy, mode, level=None, table=TEXEL_LINEAR):
    """The value (n, 4) of n pixels by `mode` (`taps`, then `gather`)."""
    found = taps(materials, tex, u, v, d_dx, d_dy, mode, level)
    return gather(materials, tex, found, table)


def triangle_level(materials, tex, uv_area2, screen_area2):
    """The level of the triangle's whole lookup (the card's today): `mip_level` of its
    doubled uv area in level-0 texels against its doubled screen area."""
    tex = np.asarray(tex, np.int64)
    width, height = sizes(materials, tex, np.zeros(len(tex), np.int64))
    texels = (np.asarray(uv_area2, F) * (width * height).astype(F)).astype(F)
    return mip_level(texels, np.asarray(screen_area2, F), materials["levels"][tex])


def reads(found):
    """Texel reads (n,) a pixel: its taps of weight above 0."""
    return (found[3] > 0).sum(axis=1)


def pages(tex, found, firsts):
    """The page (n, K) of every tap (-1 where the weight is 0), pages numbered by
    `access.texture_firsts` (firsts (N, levels, 2): first page, pages across)."""
    level, x, y, weight = found
    tex = np.asarray(tex, np.int64)[:, None]
    first, across = firsts[tex, level, 0], firsts[tex, level, 1]
    page = first + (y // PAGE) * across + x // PAGE
    return np.where(weight > 0, page, -1)
