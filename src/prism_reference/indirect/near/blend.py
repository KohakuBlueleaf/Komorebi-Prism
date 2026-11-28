"""The one-tile form blended: a pixel's E is the weighted sum over the 2 x 2 tiles around
it (one of each parity of row and column) of its row on that tile's cells and groups
times that tile's S_T; the weights a ramp `band` pixels each side of the tiles' middles.
"""

import numpy as np

from prism_reference.indirect.near.fuse import smooth
from prism_reference.indirect.near.tile import near_weights
from prism_reference.indirect.near.tile_far import tile_weights


def class_tiles(covered, tile, band):
    """The owners (4, 2, H, W) (ty, tx of the tile of each parity class (row, column)
    around each pixel) and their blend weights (4, H, W): 0 for a tile out of the frame
    or with no covered pixel, summing to 1 at a covered pixel."""
    h, w = covered.shape
    down, across = -(-h // tile), -(-w // tile)
    present = np.zeros((down * tile, across * tile), bool)
    present[:h, :w] = covered
    present = present.reshape(down, tile, across, tile).any((1, 3))
    gy, gx = np.mgrid[0:h, 0:w]
    owners, blends = [], []
    for cy in (0, 1):
        for cx in (0, 1):
            ty, by = class_axis(gy, tile, band, cy)
            tx, bx = class_axis(gx, tile, band, cx)
            inside = (ty >= 0) & (ty < down) & (tx >= 0) & (tx < across)
            ty, tx = np.clip(ty, 0, down - 1), np.clip(tx, 0, across - 1)
            owners.append([ty, tx])
            blends.append(by * bx * inside * present[ty, tx])
    blends = np.array(blends)
    return np.array(owners), blends / np.maximum(blends.sum(0), 1e-30)


def class_axis(g, tile, band, parity):
    """Along one axis: the tile of `parity` among the two whose middles hold pixel g
    between them, and its ramp weight (1 at its middle's side past `band` pixels)."""
    u = (g + 0.5 - tile / 2) / tile
    t0 = np.floor(u).astype(np.int64)
    ramp = np.clip(0.5 - (u - t0 - 0.5) * tile / (2 * band), 0.0, 1.0)
    mine = t0 % 2 == parity
    return np.where(mine, t0, t0 + 1), np.where(mine, ramp, 1.0 - ramp)


def far_rows(owner, entries, weights, covered, projections, places, columns):
    """W_far (H, W, columns): each pixel's lookup weights summed into its owner's groups;
    an entry not of the owner's goes to the owner's group of its direction whose weighted
    centre is nearest (any group when none has that direction)."""
    h, w = covered.shape
    across = int(owner[1].max()) + 1
    key_of = owner[0] * across + owner[1]
    out = np.zeros((h, w, columns))
    for key in np.unique(key_of[covered]):
        t = (int(key // across), int(key % across))
        if t not in projections:
            continue
        ys, xs = np.nonzero((key_of == key) & covered)
        use, p = projections[t]
        group = np.argmax(p, 0)
        e, wt = entries[ys, xs], weights[ys, xs]
        at = np.clip(np.searchsorted(use, e), 0, len(use) - 1)
        g = np.where(use[at] == e, group[at], -1)
        lost = (g < 0) & (wt > 0)
        if lost.any():
            g[lost] = nearest_group(p, places[use], places[e[lost]])
        sel = wt > 0
        rows = np.repeat(np.arange(len(ys)), e.shape[1]).reshape(e.shape)
        acc = np.zeros((len(ys), columns))
        np.add.at(acc, (rows[sel], g[sel]), wt[sel])
        out[ys, xs] = acc
    return out


def nearest_group(p, own, foreign):
    """The group (n,) of P (columns, m) over places `own` (m, 4) whose weighted centre is
    nearest each `foreign` place (n, 4), among those of its direction when any."""
    kept = np.nonzero(p.sum(1) > 0)[0]
    centre = (p[kept] @ own[:, :3]) / p[kept].sum(1)[:, None]
    direction = own[np.argmax(p[kept], 1), 3]
    dist = ((foreign[:, None, :3] - centre[None]) ** 2).sum(-1)
    other = direction[None] != foreign[:, 3:4]
    same = np.where(other, np.inf, dist)
    pick = np.where(np.isfinite(same.min(1)), same.argmin(1), dist.argmin(1))
    return kept[pick]


def blended_rows(op, frame, lookups, groups, k_values, form):
    """W (H, W, 4, columns) and the owners (4, 2, H, W): each class tile's rows by the
    fusion rule (smoothing bounded to the pixels of one owner) times its blend weight.
    `lookups`: entries, weights, found, covered, places; `k_values`: S of the furnace.
    """
    entries, weights, found, covered, places = lookups
    tile = form["tile"]
    owners, blends = class_tiles(covered, tile, form["band"])
    columns = None
    rows = []
    for owner, blend in zip(owners, blends):
        near = near_weights(op, covered.shape, tile, form, owner=tuple(owner))
        label = owner[0] * (int(owner[1].max()) + 1) + owner[1]
        near, blocked = smooth(
            [near, near.sum(-1)], frame, op["rule"]["filter"], label=label
        )
        columns = k_values.shape[2]
        far = far_rows(owner, entries, weights, covered, groups, places, columns)
        k = np.einsum("hwc,hwc->hw", far, k_values[owner[0], owner[1], :, 0])
        k = np.where(found, k / np.pi, 1.0)
        w_t, far_scale = tile_weights(near, blocked, far, k)
        missing = (far_scale * (covered & ~found))[..., None]
        rows.append(blend[..., None] * np.concatenate([w_t, missing], -1))
    return np.stack(rows, 2), owners


def blended_product(weights, owners, operand):
    """E (H, W, 3): the sum over the 4 class tiles of each pixel's row times its owner's
    S_T (tiles down, across, columns, 3)."""
    out = 0.0
    for c, (ty, tx) in enumerate(owners):
        out = out + np.einsum("hwc,hwcd->hwd", weights[:, :, c], operand[ty, tx])
    return out
