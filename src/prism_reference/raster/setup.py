"""Projection and triangle setup: camera space, the clip at the near distance, the
per-triangle records of edge functions, planes and pixel boxes."""

import numpy as np

from prism_reference.scene.frame import TILE, frame_grid, frame_size

F = np.float32


def grid(scene):
    """The scene's frame grid (TX, TY): the frame rendered is TILE TX by TILE TY."""
    return frame_grid(frame_size(scene))


def camera_space(scene):
    """Coordinates x, y, z (V,) float32 of the vertices along right, up, forward."""
    cam = scene["camera"]
    d = scene["positions"] - cam[0:3]
    xc = (d[:, 0] * cam[3] + d[:, 1] * cam[4]) + d[:, 2] * cam[5]
    yc = (d[:, 0] * cam[6] + d[:, 1] * cam[7]) + d[:, 2] * cam[8]
    zc = (d[:, 0] * cam[9] + d[:, 1] * cam[10]) + d[:, 2] * cam[11]
    return xc, yc, zc


def to_screen(cam, xc, yc, zc):
    """Screen x, y and 1/z of camera-space points with z beyond the near distance."""
    inv = F(1.0) / zc
    return cam[13] + cam[12] * (xc * inv), cam[14] - cam[12] * (yc * inv), inv


def world_points(cam, px, py, w):
    """Scene positions (n, 3) of pixel centres px, py at 1/z w."""
    z = F(1) / w
    xc = ((px - cam[13]) / cam[12]) * z
    yc = ((cam[14] - py) / cam[12]) * z
    return np.stack(
        [
            ((cam[k] + cam[3 + k] * xc) + cam[6 + k] * yc) + cam[9 + k] * z
            for k in range(3)
        ],
        axis=-1,
    )


def clip_polygon(corners, near):
    """The polygon (list of 6-vectors x, y, z, colour) of a triangle (3, 6) float32 cut
    at z = near; a crossing edge adds the point from its vertex beyond."""
    out = []
    for k in range(3):
        a, b = corners[k], corners[(k + 1) % 3]
        if a[2] > near:
            out.append(a)
        if (a[2] > near) != (b[2] > near):
            inside, outside = (a, b) if a[2] > near else (b, a)
            t = (near - inside[2]) / (outside[2] - inside[2])
            point = inside + t * (outside - inside)
            point[2] = near
            out.append(point.astype(np.float32))
    return out


def corners(scene, extra=None):
    """Screen x, y, 1/z and colour (R, 3) per corner of every piece, and its triangle;
    extra (T, 3, k) float32: further corner values, cut with the colour, after it."""
    cam, idx = scene["camera"], scene["indices"]
    xc, yc, zc = camera_space(scene)
    beyond = (zc > cam[15])[idx].sum(axis=1)
    whole = np.nonzero(beyond == 3)[0]
    pos = np.stack([xc, yc, zc], axis=1)
    pieces, src = [pos[idx[whole]]], [whole]
    values = scene["colors"][idx]
    if extra is not None:
        values = np.concatenate([values, extra.astype(np.float32)], axis=2)
    cols = [values[whole]]
    for t in np.nonzero((beyond == 1) | (beyond == 2))[0]:
        tri = np.concatenate([pos[idx[t]], values[t]], axis=1)
        poly = clip_polygon(tri, cam[15])
        for fan in ([0, 1, 2], [0, 2, 3])[: len(poly) - 2]:
            piece = np.stack([poly[i] for i in fan])
            pieces.append(piece[None, :, :3])
            cols.append(piece[None, :, 3:])
            src.append([t])
    pos, col, src = np.concatenate(pieces), np.concatenate(cols), np.concatenate(src)
    order = np.argsort(src, kind="stable")
    pos, col, src = pos[order], col[order], src[order]
    x, y, w = to_screen(cam, pos[..., 0], pos[..., 1], pos[..., 2])
    return x, y, w, col, src.astype(np.int64)


def planes(values, coef, inv_area):
    """The plane of per-vertex values (T, 3) over coefficients coef (T, 3)."""
    s = (coef[:, 0] * values[:, 0] + coef[:, 1] * values[:, 1]) + coef[:, 2] * values[
        :, 2
    ]
    return s * inv_area


def at(plane, px, py):
    """A plane [x, y, 1] at pixel centres: (p0 px + p1 py) + p2."""
    return (plane[:, 0] * px + plane[:, 1] * py) + plane[:, 2]


def setup(scene, extra=None):
    """Per-triangle records of the triangles that can cover a pixel (dict of arrays);
    with extra (T, 3, k) also "extra", "extra_planes" (value times 1/z) and "area2"."""
    x, y, ww, col, src = corners(scene, extra)
    cand = np.ones(len(src), dtype=bool)
    area2 = (x[:, 1] - x[:, 0]) * (y[:, 2] - y[:, 0])
    area2 = area2 - (x[:, 2] - x[:, 0]) * (y[:, 1] - y[:, 0])
    cand &= area2 != 0
    flip = area2 < 0
    order = np.where(flip[:, None], [0, 2, 1], [0, 1, 2])
    rows = np.arange(len(src))[:, None]
    x, y, ww, col = x[rows, order], y[rows, order], ww[rows, order], col[rows, order]
    area2 = np.where(flip, -area2, area2)
    lo_x = np.minimum(np.minimum(x[:, 0], x[:, 1]), x[:, 2])
    hi_x = np.maximum(np.maximum(x[:, 0], x[:, 1]), x[:, 2])
    lo_y = np.minimum(np.minimum(y[:, 0], y[:, 1]), y[:, 2])
    hi_y = np.maximum(np.maximum(y[:, 0], y[:, 1]), y[:, 2])
    half = F(0.5)
    across, down = grid(scene)
    width, height = TILE * across, TILE * down  # the padded frame
    ix0 = np.minimum(np.maximum(np.ceil(lo_x - half), F(0)), F(width)).astype(np.int64)
    ix1 = np.maximum(np.minimum(np.floor(hi_x - half), F(width - 1)), F(-1)).astype(
        np.int64
    )
    iy0 = np.minimum(np.maximum(np.ceil(lo_y - half), F(0)), F(height)).astype(np.int64)
    iy1 = np.maximum(np.minimum(np.floor(hi_y - half), F(height - 1)), F(-1)).astype(
        np.int64
    )
    cand &= (ix0 <= ix1) & (iy0 <= iy1)
    keep = np.nonzero(cand)[0]
    x, y, ww, col = x[keep], y[keep], ww[keep], col[keep]
    col, values = col[:, :, :3], col[:, :, 3:]
    area2, ix0, ix1, iy0, iy1 = (a[keep] for a in (area2, ix0, ix1, iy0, iy1))
    a_coef, b_coef, c_coef = (
        np.empty((len(keep), 3), dtype=np.float32) for _ in range(3)
    )
    for i, (p, q) in enumerate([(1, 2), (2, 0), (0, 1)]):
        a_coef[:, i] = y[:, p] - y[:, q]
        b_coef[:, i] = x[:, q] - x[:, p]
        c_coef[:, i] = -(a_coef[:, i] * x[:, p] + b_coef[:, i] * y[:, p])
    top_left = (a_coef > 0) | ((a_coef == 0) & (b_coef > 0))
    inv_area = F(1.0) / area2
    wp = np.stack([planes(ww, c, inv_area) for c in (a_coef, b_coef, c_coef)], axis=1)
    cp = np.empty((len(keep), 3, 3), dtype=np.float32)
    for ch in range(3):
        for k, c in enumerate((a_coef, b_coef, c_coef)):
            cp[:, k, ch] = planes(col[:, :, ch], c, inv_area)
    records = {
        "tri": src[keep].astype(np.int32),
        "a": a_coef,
        "b": b_coef,
        "c": c_coef,
        "top_left": top_left,
        "w_planes": wp,
        "c_planes": cp,
        "box": np.stack([ix0, ix1, iy0, iy1], axis=1).astype(np.int32),
    }
    if extra is not None:
        weighted = values * ww[:, :, None]
        ep = np.empty((len(keep), 3, values.shape[2]), dtype=np.float32)
        for j in range(values.shape[2]):
            for k, c in enumerate((a_coef, b_coef, c_coef)):
                ep[:, k, j] = planes(weighted[:, :, j], c, inv_area)
        records |= {"extra": values, "extra_planes": ep, "area2": area2}
    return records
