"""The near field at half resolution: the frame's every second pixel, and the join of its
outputs to the full frame by a depth- and normal-aware upsample."""

import numpy as np

# The settings that keep the same reach in full-resolution pixels at half resolution.
HALF_SHIFT = {"halo": 1, "coarse_level": 1, "reach_px": 1}


def half_camera(camera):
    """The camera (16,) of the half-resolution frame: focal and principal point halved."""
    out = np.asarray(camera, np.float64).copy()
    out[12:15] /= 2
    return out


def half_settings(settings):
    """March settings at half resolution: halo and reach halved, coarse level one less."""
    out = dict(settings)
    out["halo"] = settings["halo"] >> HALF_SHIFT["halo"]
    out["reach_px"] = settings["reach_px"] >> HALF_SHIFT["reach_px"]
    out["coarse_level"] = settings["coarse_level"] - HALF_SHIFT["coarse_level"]
    return out


def half_of(image):
    """The half-resolution image: every second pixel of each row and column."""
    return image[::2, ::2]


def upsample(images, depth_half, depth, normal, tile=0):
    """Half-resolution images (h, w, ...) at full resolution (H, W, ...): the 4 nearest
    half pixels, bilinear weights times depth agreement (2 % of depth) and normal^8;
    with tile > 0 (half pixels), only half pixels of the full pixel's own tile."""
    h, w = depth_half.shape
    zh = np.where(np.isfinite(depth_half), depth_half, 1e30)
    nh = half_of(normal)
    big_h, big_w = depth.shape
    gy, gx = np.mgrid[0:big_h, 0:big_w]
    fy, fx = gy / 2.0, gx / 2.0
    y0, x0 = np.floor(fy).astype(np.int64), np.floor(fx).astype(np.int64)
    total = np.zeros((big_h, big_w))
    outs = [np.zeros((big_h, big_w) + im.shape[2:]) for im in images]
    for dy in (0, 1):
        for dx in (0, 1):
            yy, xx = np.clip(y0 + dy, 0, h - 1), np.clip(x0 + dx, 0, w - 1)
            if tile > 0:
                yy = np.clip(
                    yy, (gy // 2) // tile * tile, (gy // 2) // tile * tile + tile - 1
                )
                xx = np.clip(
                    xx, (gx // 2) // tile * tile, (gx // 2) // tile * tile + tile - 1
                )
            bw = (1 - np.abs(fy - (y0 + dy))) * (1 - np.abs(fx - (x0 + dx)))
            rel = (zh[yy, xx] - depth) / (0.02 * np.abs(depth) + 1e-9)
            agree = np.maximum((nh[yy, xx] * normal).sum(-1), 0.0) ** 8
            wt = np.maximum(bw, 1e-3) * np.exp(-rel * rel) * agree + 1e-12 * bw
            total += wt
            for o, im in zip(outs, images):
                v = im[yy, xx]
                o += v * (wt if v.ndim == 2 else wt[..., None])
    return [o / (total if o.ndim == 2 else total[..., None]) for o in outs]
