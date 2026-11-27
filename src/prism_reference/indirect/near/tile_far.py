"""The far field as columns of one screen tile's product: the field lookup's own weights
onto (voxel, direction) entries, the tile's entries as columns or a rank-n basis of
them, and the whole tile's weights W_T and operand S_T with the fusion rule."""

import numpy as np

from prism_reference.indirect.field.build import voxel_keys
from prism_reference.indirect.field.values import FIELD_SHIFT
from prism_reference.indirect.near.fuse import FLOOR_K

F = np.float32
WIDTH = 32  # columns of a tile's product


def lookup_weights(model, position, normal):
    """`values.lookup` as weights: entries (n, 24) (voxel x 6 + direction), weights (n,
    24) with sum weights x values == the lookup, and where any voxel had data."""
    h, origin, dims = model["field_spacing"], model["field_origin"], model["field_dims"]
    keys, has = model["field_keys"], model["field_has"]
    n = normal.astype(F)
    g = ((position.astype(F) + n * (F(FIELD_SHIFT) * h)) - origin) / h - F(0.5)
    base = np.floor(g).astype(np.int64)
    t = g - base.astype(F)
    entries, weights = [], []
    axes = np.zeros(len(n), F)
    for a in range(3):
        d = 2 * a + (n[:, a] < 0)
        den = np.zeros(len(n), F)
        part = []
        for corner in np.ndindex(2, 2, 2):
            key = voxel_keys(base + np.array(corner), dims)
            at = np.minimum(np.searchsorted(keys, key), len(keys) - 1)
            ok = (keys[at] == key) & (key >= 0) & has[at, d]
            wc = np.prod(np.where(np.array(corner) == 1, t, F(1) - t), 1) * ok
            entries.append(at * 6 + d)
            part.append(wc)
            den += wc
        got = den > 0
        na2 = n[:, a] * n[:, a]
        scale = np.where(got, na2 / np.where(got, den, F(1)), F(0))
        weights += [wc * scale for wc in part]
        axes += np.where(got, na2, F(0))
    found = axes > 0
    w = np.stack(weights, 1) / np.where(found, axes, F(1))[:, None]
    return np.stack(entries, 1), w.astype(np.float64), found


def far_columns(entries, weights, covered, tile, columns, keep=None, places=None):
    """Per screen tile: W_far (H, W, columns), the projection (entries (m,), P (columns,
    m)) with S_far = P values[entries], and m a tile: the entries when m fits, else
    `grouped` when `places` (per entry) is given, else `basis` (exact on `keep`)."""
    h, w = covered.shape
    out = np.zeros((h, w, columns))
    projections, counts = {}, []
    for y0 in range(0, h, tile):
        for x0 in range(0, w, tile):
            cov = covered[y0 : y0 + tile, x0 : x0 + tile]
            ys, xs = np.nonzero(cov)
            if len(ys) == 0:
                continue
            e = entries[y0 + ys, x0 + xs]
            wt = weights[y0 + ys, x0 + xs]
            use, inv = np.unique(e[wt > 0], return_inverse=True)
            m = len(use)
            counts.append(m)
            dense = np.zeros((len(ys), max(m, 1)))
            rows = np.repeat(np.arange(len(ys)), e.shape[1]).reshape(e.shape)
            np.add.at(dense, (rows[wt > 0], inv), wt[wt > 0])
            if m <= columns:
                wf = np.zeros((len(ys), columns))
                wf[:, :m] = dense[:, :m]
                p = np.eye(columns, max(m, 1))
            elif places is not None:
                wf, p = grouped(dense, columns, places[use])
            else:
                wf, p = basis(dense, columns, None if keep is None else keep[use])
            out[y0 + ys, x0 + xs] = wf
            projections[(y0 // tile, x0 // tile)] = (use, p[:, : max(m, 1)])
    return out, projections, np.array(counts)


def basis(dense, columns, keep):
    """W (n, columns), P (columns, m) with W P the best rank-`columns` form of dense (n,
    m); with keep (m,): its first column dense keep, so that W P keep = dense keep."""
    if keep is None or not np.any(keep):
        u, s, vt = np.linalg.svd(dense, full_matrices=False)
        return u[:, :columns] * s[:columns], vt[:columns]
    b = keep / (keep @ keep)
    first = dense @ keep
    rest = dense - np.outer(first, b)
    u, s, vt = np.linalg.svd(rest, full_matrices=False)
    w = np.concatenate([first[:, None], u[:, : columns - 1] * s[: columns - 1]], 1)
    return w, np.concatenate([b[None], vt[: columns - 1]], 0)


def grouped(dense, columns, places):
    """W (n, columns) = the sums of dense's columns over `columns` groups of the entries
    (by direction, then halves of their voxels' box), P (columns, m) the group means
    weighted by the column sums: nonnegative, each row's sum kept."""
    weight = dense.sum(0)
    groups = np.zeros(len(places), np.int64)
    directions = np.unique(places[:, 3])
    share = np.array([weight[places[:, 3] == d].sum() for d in directions])
    count = np.ones(len(directions), np.int64)
    for _ in range(columns - len(directions)):
        count[np.argmax(share / count)] += 1
    first = 0
    for d, k in zip(directions, count):
        at = np.nonzero(places[:, 3] == d)[0]
        for part in halves(at, places[:, :3], weight, int(k)):
            groups[part] = first
            first += 1
    w = np.zeros((len(dense), columns))
    p = np.zeros((columns, len(places)))
    for g in range(first):
        sel = groups == g
        if not sel.any():
            continue
        w[:, g] = dense[:, sel].sum(1)
        total = weight[sel].sum()
        p[g, sel] = weight[sel] / total if total > 0 else 1.0 / sel.sum()
    return w, p


def halves(at, xyz, weight, k):
    """The entries `at` in k parts: split along their box's longest side at the weighted
    share of the first part's count, recursively."""
    if k <= 1 or len(at) <= 1:
        return [at] + [at[:0]] * (k - 1)
    box = xyz[at]
    axis = int(np.argmax(box.max(0) - box.min(0)))
    order = at[np.argsort(box[:, axis], kind="stable")]
    cum = np.cumsum(weight[order] + 1e-30)
    k1 = k // 2
    cut = int(np.searchsorted(cum, cum[-1] * k1 / k)) + 1
    cut = min(max(cut, 1), len(order) - 1)
    return halves(order[:cut], xyz, weight, k1) + halves(
        order[cut:], xyz, weight, k - k1
    )


def entry_places(model):
    """Each field entry's (voxel x 6 + direction) voxel centre and direction (nv x 6, 4)."""
    h, origin, dims = model["field_spacing"], model["field_origin"], model["field_dims"]
    ijk = np.stack(np.unravel_index(model["field_keys"], tuple(dims)), -1)
    centre = origin + (ijk + 0.5) * h
    out = np.zeros((len(centre), 6, 4))
    out[:, :, :3] = centre[:, None]
    out[:, :, 3] = np.arange(6)
    return out.reshape(-1, 4)


def far_values(projections, values, shape, tile, columns):
    """S_far (tiles down, tiles across, columns, 3) of the field's values (nv, 6, 3)."""
    flat = values.reshape(-1, values.shape[-1]).astype(np.float64)
    out = np.zeros((-(-shape[0] // tile), -(-shape[1] // tile), columns, flat.shape[1]))
    for (ty, tx), (use, p) in projections.items():
        if len(use):
            out[ty, tx] = p[:, : len(use)] @ flat[use]
    return out


def tile_weights(near, blocked, far, k):
    """W_T (H, W, near + far columns) by the fusion rule: pi W_near and (1 - blocked) /
    K W_far; where K < FLOOR_K the near hits' mean (W_near / blocked), or W_far alone.
    """
    k = k[..., 0] if k.ndim == 3 else k
    low = k < FLOOR_K
    hit = blocked > 0
    near_scale = np.divide(1.0, blocked, out=np.ones_like(blocked), where=low & hit)
    far_scale = np.where(
        low, np.where(hit, 0.0, 1.0), (1.0 - blocked) / np.maximum(k, FLOOR_K)
    )
    return (
        np.concatenate(
            [np.pi * near * near_scale[..., None], far * far_scale[..., None]], -1
        ),
        far_scale,
    )


def product(weights, values, tile):
    """E (H, W, 3): each pixel's row of W_T times its tile's S_T."""
    h, w = weights.shape[:2]
    ty, tx = np.arange(h) // tile, np.arange(w) // tile
    return np.einsum("hwc,hwcd->hwd", weights, values[ty[:, None], tx[None, :]])
