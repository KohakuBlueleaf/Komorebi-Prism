"""The field's values for element irradiance, and the lookup a pixel makes."""

import numpy as np

from prism_reference.indirect.field.build import voxel_keys

F = np.float32
FIELD_SHIFT = 0.5  # the lookup point's shift along the normal, in voxels


def field_values(model, e):
    """The field's values (nv, 6, 3) float32 for element irradiance e (N, 3)."""
    rows, cols, w = (model[f"field_{k}"] for k in ("rows", "columns", "weights"))
    size = len(model["field_keys"]) * 6
    out = np.stack(
        [np.bincount(rows, w * e[cols, c], size) for c in range(e.shape[1])], -1
    )
    return out.reshape(-1, 6, e.shape[1]).astype(F)


def lookup(model, values, position, normal):
    """I (n, 3) float32 at points P with normals n, and where any voxel had data: the 8
    voxels around P + n h / 2, trilinear, per axis the direction of n's sign, blended
    by n_a^2 over the axes that found data."""
    h, origin, dims = model["field_spacing"], model["field_origin"], model["field_dims"]
    keys, has = model["field_keys"], model["field_has"]
    n = normal.astype(F)
    g = ((position.astype(F) + n * (F(FIELD_SHIFT) * h)) - origin) / h - F(0.5)
    base = np.floor(g).astype(np.int64)
    t = g - base.astype(F)
    total = np.zeros((len(n), values.shape[2]), F)
    axes = np.zeros(len(n), F)
    for a in range(3):
        d = 2 * a + (n[:, a] < 0)
        num = np.zeros_like(total)
        den = np.zeros(len(n), F)
        for corner in np.ndindex(2, 2, 2):
            key = voxel_keys(base + np.array(corner), dims)
            at = np.minimum(np.searchsorted(keys, key), len(keys) - 1)
            ok = (keys[at] == key) & (key >= 0) & has[at, d]
            wc = np.prod(np.where(np.array(corner) == 1, t, F(1) - t), 1) * ok
            num += wc[:, None] * values[at, d]
            den += wc
        got = den > 0
        na2 = n[:, a] * n[:, a]
        total += np.where(got, na2 / np.where(got, den, F(1)), F(0))[:, None] * num
        axes += np.where(got, na2, F(0))
    found = axes > 0
    return total / np.where(found, axes, F(1))[:, None], found
