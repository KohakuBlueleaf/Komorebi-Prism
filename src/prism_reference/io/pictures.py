"""Pictures of a frame's arrays: a colour map for scalar images, depth, tile load,
where two outputs differ, and box downscaling."""

import re

import numpy as np

from prism_reference.post.display import to_srgb8
from prism_reference.scene.frame import TILE

# Anchor colours of a perceptual colour map (dark to bright), interpolated linearly.
VIRIDIS = np.array(
    [
        [68, 1, 84],
        [72, 36, 117],
        [65, 68, 135],
        [53, 95, 141],
        [42, 120, 142],
        [33, 145, 140],
        [34, 168, 132],
        [68, 191, 112],
        [122, 209, 81],
        [189, 223, 38],
        [253, 231, 37],
    ],
    dtype=np.float64,
)


def colormap(values, low=None, high=None):
    """Maps a float image to RGB uint8 with the VIRIDIS anchors between low and high."""
    values = np.asarray(values, dtype=np.float64)
    low = float(values.min()) if low is None else low
    high = float(values.max()) if high is None else high
    x = np.clip((values - low) / max(high - low, 1e-30), 0.0, 1.0)
    pos = x * (len(VIRIDIS) - 1)
    i = np.minimum(pos.astype(np.int64), len(VIRIDIS) - 2)
    frac = (pos - i)[..., None]
    rgb = VIRIDIS[i] * (1 - frac) + VIRIDIS[i + 1] * frac
    return np.rint(rgb).astype(np.uint8)


def downscale(image, factor):
    """Box-filter downscale of a (H, W, 3) uint8 or float image by an integer factor."""
    h, w = image.shape[:2]
    shape = (h // factor, factor, w // factor, factor) + image.shape[2:]
    out = image.reshape(shape).astype(np.float64).mean(axis=(1, 3))
    return np.rint(out).astype(np.uint8) if image.dtype == np.uint8 else out


def depth_picture(depth):
    """Log of the view distance 1/w on the viridis map; empty pixels black."""
    hit = depth > 0
    z = np.log(1.0 / np.where(hit, depth, 1.0))
    rgb = colormap(z, z[hit].min(), z[hit].max())
    rgb[~hit] = 0
    return rgb, {
        "z_min": float(np.exp(z[hit].min())),
        "z_max": float(np.exp(z[hit].max())),
    }


def diff_picture(colour, mask):
    """The colour image dimmed, with differing pixels (grown by 2) in red."""
    base = (to_srgb8(colour) * 0.35).astype(np.uint8)
    grown = mask.copy()
    for _ in range(2):
        grown[1:] |= grown[:-1]
        grown[:-1] |= grown[1:]
        grown[:, 1:] |= grown[:, :-1]
        grown[:, :-1] |= grown[:, 1:]
    base[grown] = [255, 40, 40]
    return base


def tiles_picture(counts):
    """Triangles per tile on the viridis map of log(1 + count), one block per tile."""
    rgb = colormap(np.log1p(counts.astype(np.float64)), 0.0, None)
    big = np.repeat(np.repeat(rgb, TILE, axis=0), TILE, axis=1)
    return big, {
        "tile_max": int(counts.max()),
        "tile_nonempty": int((counts > 0).sum()),
    }


def slug(name):
    """A file-name form of an implementation name."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower().replace("+", "p")).strip("_")
