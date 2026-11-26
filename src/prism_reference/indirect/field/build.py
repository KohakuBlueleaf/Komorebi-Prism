"""The field's build: voxels around the elements, the weights from elements to (voxel,
direction) values (only the elements a voxel's centre sees), empty directions filled
from a neighbour."""

import numpy as np

from prism_reference.trace.batch import trace

F = np.float32
# Radius in voxels, reach of the fill of empty directions, the six directions.
FIELD_RADIUS = 2.0
FILL_REACH = 2.0
DIRECTIONS = np.array(
    [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]], dtype=F
)


def voxel_keys(ijk, dims):
    """Keys (...,) of voxel indices (..., 3) in a grid of dims (3,); -1 outside it."""
    inside = ((ijk >= 0) & (ijk < dims)).all(-1)
    key = (ijk[..., 0] * dims[1] + ijk[..., 1]) * dims[2] + ijk[..., 2]
    return np.where(inside, key, -1)


def sight(tree, eps, position, normal):
    """seen(centres (n, 3), columns (n,)) for `build_field`: one any-hit ray from the
    voxel's centre to the element's point moved eps along its normal; an element hidden
    from the centre (under a floor, past a corner, behind a picture) does not count."""

    def seen(centre, column):
        end = position[column].astype(np.float64)
        end = end + normal[column].astype(np.float64) * eps
        _, tri, _, _ = trace(tree, centre.astype(F), (end - centre).astype(F), 1.0, True)
        return tri < 0

    return seen


def build_field(position, normal, spacing, chunk=2000, seen=None):
    """The sparse field of voxels of side h = spacing: (voxel, d) = sum w E / sum w over
    the elements within FIELD_RADIUS h; rows (voxel x 6 + d), columns, weights; keys,
    has, grid. `seen(centres (n, 3), columns (n,))`: the (voxel, element) pairs that
    count (`sight`; None: all).
    """
    h = float(spacing)
    radius = FIELD_RADIUS * h
    p, nrm = position.astype(np.float64), normal.astype(np.float64)
    origin = np.floor(p.min(0) / h) * h - 2 * h
    dims = (np.ceil((p.max(0) - origin) / h) + 3).astype(np.int64)
    reach = int(np.ceil(2 * radius / h)) + 2
    offsets = np.stack(np.meshgrid(*(np.arange(reach),) * 3, indexing="ij"), -1)
    offsets = offsets.reshape(-1, 3)
    keys, columns, weights = [], [], []
    for s in range(0, len(p), chunk):
        q, n = p[s : s + chunk], nrm[s : s + chunk]
        corner = np.floor((q - radius - origin) / h - 0.5).astype(np.int64)
        ijk = corner[:, None, :] + offsets[None]
        r = np.linalg.norm(origin + (ijk + 0.5) * h - q[:, None, :], axis=-1) / radius
        fall = np.where(r < 1, (1 - r * r) ** 2, 0.0)
        w = (
            fall[:, :, None]
            * np.maximum(n @ DIRECTIONS.T.astype(np.float64), 0)[:, None]
        )
        e, o = np.nonzero(fall > 0)
        keys.append(voxel_keys(ijk[e, o], dims))
        columns.append(e + s)
        weights.append(w[e, o])
    key, column, w = (
        np.concatenate(keys),
        np.concatenate(columns),
        np.concatenate(weights),
    )
    some = (w.sum(1) > 0) & (key >= 0)
    if seen is not None:
        at = np.nonzero(some)[0]
        ijk = np.stack(np.unravel_index(key[at], tuple(dims)), -1)
        some[at] = seen(origin + (ijk + 0.5) * h, column[at])
    voxels, voxel = np.unique(key[some], return_inverse=True)
    rows = (voxel[:, None] * 6 + np.arange(6)).ravel()
    column, w = np.repeat(column[some], 6), w[some].ravel()
    rows, column, w = rows[w > 0], column[w > 0], w[w > 0]
    total = np.bincount(rows, w, len(voxels) * 6)
    own = (total > 0).reshape(-1, 6)
    w = w / total[rows]
    rows, column, w, source = fill_rows(voxels, own, dims, rows, column, w)
    order = np.argsort(rows, kind="stable")
    has = np.zeros(len(voxels) * 6, dtype=bool)
    has[rows] = True
    return {
        "field_origin": origin.astype(F),
        "field_spacing": np.float32(h),
        "field_dims": dims,
        "field_keys": voxels.astype(np.int64),
        "field_has": has.reshape(-1, 6),
        "field_own": own,
        "field_rows": rows[order].astype(np.int64),
        "field_columns": column[order].astype(np.int32),
        "field_weights": w[order].astype(F),
        "field_filled_from": source,
    }


def fill_rows(voxels, own, dims, rows, column, w):
    """The rows of `build_field` with each empty (voxel, d) given the row of the nearest
    voxel within FILL_REACH whose d has elements; also each filled one's source voxel.
    """
    span = int(FILL_REACH)
    grid = np.arange(-span, span + 1)
    offsets = np.stack(np.meshgrid(grid, grid, grid, indexing="ij"), -1).reshape(-1, 3)
    d2 = (offsets * offsets).sum(1)
    keep = (d2 > 0) & (d2 <= FILL_REACH**2)
    offsets = offsets[keep][np.lexsort((*offsets[keep].T[::-1], d2[keep]))]
    ijk = np.stack(np.unravel_index(voxels, tuple(dims)), -1)
    source = np.full(own.shape, -1, dtype=np.int64)
    for offset in offsets:
        missing = (~own) & (source < 0)
        if not missing.any():
            break
        key = voxel_keys(ijk + offset, dims)
        at = np.minimum(np.searchsorted(voxels, key), len(voxels) - 1)
        found = (voxels[at] == key) & (key >= 0)
        take = missing & found[:, None] & own[at]
        source[take] = np.broadcast_to(at[:, None], own.shape)[take]
    order = np.argsort(rows, kind="stable")
    start = np.searchsorted(rows[order], np.arange(own.size + 1))
    v, d = np.nonzero(source >= 0)
    src_row = source[v, d] * 6 + d
    count = start[src_row + 1] - start[src_row]
    pick = np.repeat(start[src_row], count) + (
        np.arange(count.sum()) - np.repeat(np.cumsum(count) - count, count)
    )
    new_rows = np.repeat(v * 6 + d, count)
    rows = np.concatenate([rows, new_rows])
    column = np.concatenate([column, column[order][pick]])
    w = np.concatenate([w, w[order][pick]])
    return rows, column, w, source.astype(np.int32)


def field_counts(model):
    """Voxels and weights of the field."""
    return {
        "voxels": len(model["field_keys"]),
        "voxel_directions_own": int(model["field_own"].sum()),
        "voxel_directions_filled": int((model["field_filled_from"] >= 0).sum()),
        "field_weights": len(model["field_weights"]),
    }
