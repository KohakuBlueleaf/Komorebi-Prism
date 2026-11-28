"""Projection and triangle setup: camera space, the clip at the near distance, the
per-triangle records of edge functions, planes and pixel boxes."""

import concurrent.futures
import os

import numpy as np

from prism_reference.scene.frame import TILE, frame_grid, frame_size

F = np.float32
HELD_LEAST = F(1 - 2**-16)  # a drawn 1/z is held within these of its corners' range
HELD_MOST = F(1 + 2**-16)


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


def clip_corners(corners, near):
    """The polygon of a triangle's camera-space corners (3, 3) float32 cut at z = near:
    each point's position and its recipe (from, to, t), a kept corner's to its from."""
    out = []
    for k in range(3):
        a, b = corners[k], corners[(k + 1) % 3]
        if a[2] > near:
            out.append((a, k, k, F(0)))
        if (a[2] > near) != (b[2] > near):
            i, o = (k, (k + 1) % 3) if a[2] > near else ((k + 1) % 3, k)
            inside, outside = corners[i], corners[o]
            t = (near - inside[2]) / (outside[2] - inside[2])
            point = inside + t * (outside - inside)
            point[2] = near
            out.append((point.astype(np.float32), i, o, t))
    return out


def screen_pieces(scene, recipes=True, space=None):
    """Screen x, y, 1/z (R, 3) per corner of every piece, its triangle, and each
    corner's recipe: the triangle's corners from, to (R, 3) and t (R, 3) float32 (None
    without `recipes`); `space` the vertices' `camera_space` when already made."""
    cam, idx = scene["camera"], scene["indices"]
    xc, yc, zc = camera_space(scene) if space is None else space
    inside = (zc > cam[15])[idx]
    beyond = inside[:, 0].astype(np.int8) + inside[:, 1] + inside[:, 2]
    whole = np.nonzero(beyond == 3)[0]
    pos = np.stack([xc, yc, zc], axis=1)
    kept = np.broadcast_to(np.arange(3, dtype=np.int8), (len(whole), 3))
    pieces, src = [pos[idx[whole]]], [whole]
    froms, tos, ts = [kept], [kept], [np.zeros((len(whole), 3), dtype=np.float32)]
    for t in np.nonzero((beyond == 1) | (beyond == 2))[0]:
        poly = clip_corners(pos[idx[t]], cam[15])
        for fan in ([0, 1, 2], [0, 2, 3])[: len(poly) - 2]:
            points = [poly[i] for i in fan]
            pieces.append(np.stack([p[0] for p in points])[None])
            froms.append(np.array([[p[1] for p in points]], dtype=np.int8))
            tos.append(np.array([[p[2] for p in points]], dtype=np.int8))
            ts.append(np.array([[p[3] for p in points]], dtype=np.float32))
            src.append([t])
    recipe = (kept, kept, ts[0]) if recipes else None
    if len(src) == 1:
        pos, src = pieces[0], whole
    else:
        pos, src = np.concatenate(pieces), np.concatenate(src)
        order = np.argsort(src, kind="stable")
        pos, src = pos[order], src[order]
        if recipes:
            recipe = tuple(np.concatenate(p)[order] for p in (froms, tos, ts))
    x, y, w = to_screen(cam, pos[..., 0], pos[..., 1], pos[..., 2])
    return x, y, w, src.astype(np.int64), recipe


def corners(scene, extra=None):
    """Screen x, y, 1/z and colour (R, 3) per corner of every piece, and its triangle;
    extra (T, 3, k) float32: further corner values, cut with the colour, after it."""
    x, y, w, src, (froms, tos, ts) = screen_pieces(scene)
    values = scene["colors"][scene["indices"]]
    if extra is not None:
        values = np.concatenate([values, extra.astype(np.float32)], axis=2)
    rows = src[:, None]
    start, end = values[rows, froms], values[rows, tos]
    cut = (froms != tos)[:, :, None]
    col = np.where(cut, start + ts[:, :, None] * (end - start), start)
    return x, y, w, col, src


def planes(values, coef, inv_area):
    """The plane of per-vertex values (T, 3) over coefficients coef (T, 3)."""
    s = (coef[:, 0] * values[:, 0] + coef[:, 1] * values[:, 1]) + coef[:, 2] * values[
        :, 2
    ]
    return s * inv_area


def at(plane, px, py):
    """A plane [x, y, 1] at pixel centres: (p0 px + p1 py) + p2."""
    return (plane[:, 0] * px + plane[:, 1] * py) + plane[:, 2]


def doubled_area(x, y):
    """The doubled signed area (R,) of every piece's screen corners x, y (R, 3)."""
    area2 = (x[:, 1] - x[:, 0]) * (y[:, 2] - y[:, 0])
    return area2 - (x[:, 2] - x[:, 0]) * (y[:, 1] - y[:, 0])


def pixel_bounds(scene, x, y):
    """The first and last pixel columns and rows (ix0, ix1, iy0, iy1) int64 every
    piece's screen corners x, y (R, 3) can cover in the scene's padded frame."""
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
    return ix0, ix1, iy0, iy1


def boxes(scene):
    """The pixel boxes (R, 4) int32 x0, x1, y0, y1 of the records `setup(scene)` keeps,
    from the pieces' positions alone; runs of triangles on the process's CPUs."""
    space, idx = camera_space(scene), scene["indices"]

    def run(first, end):
        part = {**scene, "indices": idx[first:end]}
        x, y, _, _, _ = screen_pieces(part, recipes=False, space=space)
        ix0, ix1, iy0, iy1 = pixel_bounds(scene, x, y)
        keep = (doubled_area(x, y) != 0) & (ix0 <= ix1) & (iy0 <= iy1)
        return np.stack([ix0, ix1, iy0, iy1], axis=1)[keep].astype(np.int32)

    cuts = np.linspace(0, len(idx), len(os.sched_getaffinity(0)) + 1).astype(np.int64)
    with concurrent.futures.ThreadPoolExecutor(len(cuts) - 1) as pool:
        return np.concatenate(list(pool.map(run, cuts[:-1], cuts[1:])))


def depth_planes(scene, triangles):
    """The 1/z planes [x, y, 1] (T, 3) float32 of `triangles` from their own
    camera-space planes n . p = n . v0 (n = (v1 - v0) x (v2 - v0)): along a pixel's ray
    r = ((px - cx) / f, (cy - py) / f, 1), 1/z = (n . r) / (n . v0); a plane through
    the eye (n . v0 = 0) gives 0, which the drawn 1/z's bounds lift to the corners'."""
    cam = scene["camera"]
    xc, yc, zc = camera_space(scene)
    corner = scene["indices"][triangles]
    v = [
        np.stack([xc[corner[:, k]], yc[corner[:, k]], zc[corner[:, k]]])
        for k in range(3)
    ]
    e1, e2 = v[1] - v[0], v[2] - v[0]
    n = [
        e1[(i + 1) % 3] * e2[(i + 2) % 3] - e1[(i + 2) % 3] * e2[(i + 1) % 3]
        for i in range(3)
    ]
    d = (n[0] * v[0][0] + n[1] * v[0][1]) + n[2] * v[0][2]
    with np.errstate(divide="ignore"):
        t = np.where(d == 0, F(0), F(1) / d)
    u = t * (F(1) / cam[12])
    a, b = n[0] * u, -(n[1] * u)
    c = n[2] * t - (a * cam[13] + b * cam[14])
    return np.stack([a, b, c], axis=1).astype(F)


def setup(scene, extra=None):
    """Per-triangle records of the triangles that can cover a pixel (dict of arrays;
    "w_planes": the 1/z plane of the piece's triangle (depth_planes), not of the
    piece's corners; "w_range": the least and most 1/z of its corners times HELD_LEAST
    and HELD_MOST, which its drawn 1/z is held between);
    with extra (T, 3, k) also "extra", "extra_planes" (value times 1/z) and "area2"."""
    x, y, ww, col, src = corners(scene, extra)
    cand = np.ones(len(src), dtype=bool)
    area2 = doubled_area(x, y)
    cand &= area2 != 0
    flip = area2 < 0
    order = np.where(flip[:, None], [0, 2, 1], [0, 1, 2])
    rows = np.arange(len(src))[:, None]
    x, y, ww, col = x[rows, order], y[rows, order], ww[rows, order], col[rows, order]
    area2 = np.where(flip, -area2, area2)
    ix0, ix1, iy0, iy1 = pixel_bounds(scene, x, y)
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
    wp = depth_planes(scene, src[keep])
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
        "w_range": np.stack(
            [ww.min(axis=1) * HELD_LEAST, ww.max(axis=1) * HELD_MOST], axis=1
        ).astype(F),
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
