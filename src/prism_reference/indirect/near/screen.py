"""The frame as the near field reads it: camera-space points and normals, and the coarse
copy of the whole frame (nearest and farthest depth, mean radiance a cell)."""

import numpy as np

F = np.float32


def camera_axes(camera):
    """Eye (3,), the axes (3, 3) as columns (right, up, ahead), focal, cx, cy."""
    c = np.asarray(camera, np.float64)
    return c[0:3], np.stack([c[3:6], c[6:9], c[9:12]], 1), c[12], c[13], c[14]


def camera_space(camera, position, normal, covered):
    """Points and normals (H, W, 3) float64 in the camera's axes (x right, y up, z ahead)
    and the depth z (H, W), inf where nothing is covered."""
    eye, axes, _, _, _ = camera_axes(camera)
    p = (position.astype(np.float64) - eye) @ axes
    n = normal.astype(np.float64) @ axes
    z = np.where(covered, p[..., 2], np.inf)
    return p, n, z


def padded(a, level, value):
    """a (H, W, ...) padded with `value` to sides that are multiples of 2^level."""
    s = 1 << level
    h, w = a.shape[:2]
    width = [(0, -h % s), (0, -w % s)] + [(0, 0)] * (a.ndim - 2)
    return np.pad(a, width, constant_values=value)


def cells(a, level):
    """a (H', W', ...) (sides multiples of 2^level) as (h, w, 2^level * 2^level, ...)."""
    s = 1 << level
    h, w = a.shape[0] // s, a.shape[1] // s
    b = a.reshape(h, s, w, s, *a.shape[2:]).swapaxes(1, 2)
    return b.reshape(h, w, s * s, *a.shape[2:])


def coarse_depth(z, point, level):
    """The coarse copy's depths at `level`: nearest (h, w), inf where the cell is empty,
    farthest (h, w) of the covered pixels, and the nearest pixel's point (h, w, 3)."""
    zc = cells(padded(z, level, np.inf), level)
    pc = cells(padded(point, level, 0.0), level)
    at = zc.argmin(axis=2)
    near = np.take_along_axis(zc, at[..., None], 2)[..., 0]
    nearest = np.take_along_axis(pc, at[..., None, None], 2)[:, :, 0]
    far = np.where(np.isfinite(zc), zc, -np.inf).max(axis=2)
    return near, far, nearest


def coarse_radiance(radiance, z, level):
    """The coarse copy's radiance at `level`: the mean (h, w, 3) over covered pixels."""
    covered = cells(padded(np.isfinite(z), level, False), level)
    rad = cells(padded(radiance.astype(np.float64), level, 0.0), level)
    total = (rad * covered[..., None]).sum(axis=2)
    count = covered.sum(axis=2)
    return total / np.maximum(count, 1)[..., None]
