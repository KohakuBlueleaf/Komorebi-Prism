"""Sampling a texture of the scene description: its float mip chain and the nearest,
trilinear and anisotropic filters over a pixel's uv footprint."""

import numpy as np

from prism_reference.scene.artist.materials import image_bytes, srgb_to_linear
from prism_reference.scene.description.types import Sampler
from prism_reference.scene.public.textures import decode_image

COLOUR, DATA = "colour", "data"
MOST_TAPS = 16
TINY = 1e-12


def rgba(pixels):
    """uint8 (H, W, C), C = 1 to 4, as (H, W, 4): grey to rgb, alpha 255 when absent."""
    channels = pixels.shape[2]
    grey = pixels[:, :, :1]
    rgb = pixels[:, :, :3] if channels >= 3 else np.repeat(grey, 3, axis=2)
    if channels in (2, 4):
        alpha = pixels[:, :, -1:]
    else:
        alpha = np.full(pixels.shape[:2] + (1,), 255, np.uint8)
    return np.concatenate([rgb, alpha], axis=2)


def halved(level):
    """A (H, W, 4) float32 level box-filtered 2 x 2 to half size (a side of 1 stays 1)."""
    height, width = level.shape[:2]
    rows, columns = (2 if height > 1 else 1), (2 if width > 1 else 1)
    h, w = height // rows, width // columns
    block = level[: h * rows, : w * columns].reshape(h, rows, w, columns, 4)
    return block.mean(axis=(1, 3), dtype=np.float64).astype(np.float32)


class Texture:
    """A mip chain (list of (H, W, 4) float32 levels, 0 the largest) in a role: COLOUR
    (rgb linear, the sRGB transfer undone) or DATA (the bytes / 255)."""

    def __init__(self, pixels, role):
        texels = rgba(np.asarray(pixels, dtype=np.uint8))
        level = texels.astype(np.float32) / np.float32(255.0)
        if role == COLOUR:
            level[:, :, :3] = srgb_to_linear(texels[:, :, :3]).astype(np.float32)
        self.role = role
        self.levels = [level]
        while level.shape[0] > 1 or level.shape[1] > 1:
            level = halved(level)
            self.levels.append(level)

    @classmethod
    def of_image(cls, image, role):
        """The Texture of a description Image, decoded by `decode_image`."""
        return cls(decode_image(image_bytes(image)), role)


def wrapped(i, n, mode):
    """Integer texel coordinates i wrapped into 0 .. n - 1 by a glTF wrap mode."""
    if mode == "CLAMP":
        return np.clip(i, 0, n - 1)
    if mode == "MIRROR":
        m = np.mod(i, 2 * n)
        return np.where(m >= n, 2 * n - 1 - m, m)
    return np.mod(i, n)


def bilinear(level, sampler, uv):
    """The bilinear value (N, 4) of one level at uv (N, 2), texel centres at
    ((x + 0.5) / W, (y + 0.5) / H), row 0 at v = 0."""
    height, width = level.shape[:2]
    x = uv[:, 0] * width - 0.5
    y = uv[:, 1] * height - 0.5
    x0, y0 = np.floor(x), np.floor(y)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    x0, y0 = x0.astype(np.int64), y0.astype(np.int64)
    xs = [wrapped(x0, width, sampler.wrap_s), wrapped(x0 + 1, width, sampler.wrap_s)]
    ys = [wrapped(y0, height, sampler.wrap_t), wrapped(y0 + 1, height, sampler.wrap_t)]
    top = level[ys[0], xs[0]] * (1 - fx) + level[ys[0], xs[1]] * fx
    bottom = level[ys[1], xs[0]] * (1 - fx) + level[ys[1], xs[1]] * fx
    return top * (1 - fy) + bottom * fy


def at_level(texture, sampler, uv, lod):
    """The trilinear value (N, 4) at uv: bilinear in levels floor(lod) and the next,
    lod clamped to the chain."""
    last = len(texture.levels) - 1
    lod = np.clip(np.nan_to_num(lod, nan=0.0, posinf=last, neginf=0.0), 0, last)
    low = np.floor(lod).astype(np.int64)
    part = (lod - low)[:, None]
    out = np.zeros((len(uv), 4))
    for level in np.unique(low):
        pick = low == level
        a = bilinear(texture.levels[level], sampler, uv[pick])
        if level == last:
            out[pick] = a
            continue
        b = bilinear(texture.levels[level + 1], sampler, uv[pick])
        out[pick] = a * (1 - part[pick]) + b * part[pick]
    return out


def finite_uv(uv):
    """uv (N, 2) float64 with non-finite values as 0."""
    return np.nan_to_num(np.asarray(uv, dtype=np.float64), nan=0.0, posinf=0.0)


def footprint(texture, duv_dx, duv_dy):
    """The footprint's axes in level-0 texels: their lengths (N,) and uv vectors."""
    height, width = texture.levels[0].shape[:2]
    scale = np.array([width, height], dtype=np.float64)
    dx, dy = finite_uv(duv_dx), finite_uv(duv_dy)
    return (
        np.linalg.norm(dx * scale, axis=1),
        np.linalg.norm(dy * scale, axis=1),
        dx,
        dy,
    )


def nearest(texture, sampler, uv, duv_dx=None, duv_dy=None):
    """The level-0 texel (N, 4) holding uv, no mip level."""
    sampler = sampler or Sampler()
    level = texture.levels[0]
    height, width = level.shape[:2]
    uv = finite_uv(uv)
    x = wrapped(np.floor(uv[:, 0] * width).astype(np.int64), width, sampler.wrap_s)
    y = wrapped(np.floor(uv[:, 1] * height).astype(np.int64), height, sampler.wrap_t)
    return level[y, x].astype(np.float64)


def trilinear(texture, sampler, uv, duv_dx, duv_dy):
    """The isotropic trilinear value (N, 4): the level from the footprint's major axis."""
    sampler = sampler or Sampler()
    len_x, len_y, _, _ = footprint(texture, duv_dx, duv_dy)
    lod = np.log2(np.maximum(np.maximum(len_x, len_y), TINY))
    return at_level(texture, sampler, finite_uv(uv), lod)


def sample(texture, sampler, uv, duv_dx, duv_dy, most=MOST_TAPS):
    """The anisotropic value (N, 4): the level from the footprint's minor axis (at least
    major / most), up to `most` trilinear taps spread evenly along its major axis."""
    sampler = sampler or Sampler()
    uv = finite_uv(uv)
    len_x, len_y, dx, dy = footprint(texture, duv_dx, duv_dy)
    x_major = len_x >= len_y
    major = np.where(x_major, len_x, len_y)
    minor = np.maximum(np.where(x_major, len_y, len_x), major / most)
    axis = np.where(x_major[:, None], dx, dy)
    taps = np.clip(np.ceil(major / np.maximum(minor, TINY) - 1e-9), 1, most)
    taps = taps.astype(np.int64)
    lod = np.log2(np.maximum(minor, TINY))
    out = np.zeros((len(uv), 4))
    for count in np.unique(taps):
        pick = np.nonzero(taps == count)[0]
        total = np.zeros((len(pick), 4))
        for i in range(count):
            offset = (i + 0.5) / count - 0.5
            at = uv[pick] + axis[pick] * offset
            total += at_level(texture, sampler, at, lod[pick])
        out[pick] = total / count
    return out


FILTERS = {"nearest": nearest, "trilinear": trilinear, "anisotropic": sample}
