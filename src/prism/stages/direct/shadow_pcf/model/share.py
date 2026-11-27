"""The numpy twin of kernels/share.hpp: a map's 2 x 2 taps (keys (1 + page) << 10 |
texel, 0 outside; fractions) from a point through one map's camera, or from map
coordinates whose map's numbers are each lane's own."""

import numpy as np

F = np.float32
PAGE = 32  # a map page: 32 x 32 texels
PAGE_SHIFT = 10  # a key: page << 10 | texel
TAPS = 4  # tap t = dx + 2 dy


def project(points, normals, camera, texel):
    """Map coordinates sx, sy and 1/z (n,) float32 of points (n, 3) moved `texel`
    (world size) along their normals (n, 3) by a map's camera (16,)."""
    cam = np.asarray(camera, F)
    d = (points.astype(F) + normals.astype(F) * F(texel)) - cam[0:3]
    xc = (d[:, 0] * cam[3] + d[:, 1] * cam[4]) + d[:, 2] * cam[5]
    yc = (d[:, 0] * cam[6] + d[:, 1] * cam[7]) + d[:, 2] * cam[8]
    zc = (d[:, 0] * cam[9] + d[:, 1] * cam[10]) + d[:, 2] * cam[11]
    w = F(1) / zc
    sx = cam[13] + cam[12] * (xc * w)
    sy = cam[14] - cam[12] * (yc * w)
    return sx.astype(F), sy.astype(F), w.astype(F)


def coordinate_taps(sx, sy, first, across, width, height):
    """Keys (n, 4) uint32 and fractions fx, fy (n,) float32 of the 2 x 2 taps at map
    coordinates sx, sy; first (first page + 1), across (pages a row), width, height
    (texels): scalars or each lane's (n,)."""
    gx, gy = np.asarray(sx, F) - F(0.5), np.asarray(sy, F) - F(0.5)
    x0, y0 = np.floor(gx), np.floor(gy)
    fx, fy = (gx - x0).astype(F), (gy - y0).astype(F)
    x0, y0 = x0.astype(np.int64), y0.astype(np.int64)
    first = np.asarray(first, np.int64)
    across = np.asarray(across, np.int64)
    width = np.asarray(width, np.int64)
    height = np.asarray(height, np.int64)
    keys = np.zeros((len(x0), TAPS), np.uint32)
    for tap in range(TAPS):
        x, y = x0 + (tap & 1), y0 + (tap >> 1)
        inside = (x >= 0) & (x < width) & (y >= 0) & (y < height)
        page = first + (y // PAGE) * across + x // PAGE
        texel = (y % PAGE) * PAGE + x % PAGE
        key = (page << PAGE_SHIFT) | texel
        keys[:, tap] = np.where(inside, key, 0).astype(np.uint32)
    return keys, fx, fy


def point_taps(points, normals, camera, texel, first, across, width, height):
    """coordinate_taps of points through one map's camera: keys, fx, fy, and 1/z."""
    sx, sy, w = project(points, normals, camera, texel)
    keys, fx, fy = coordinate_taps(sx, sy, first, across, width, height)
    return keys, fx, fy, w
