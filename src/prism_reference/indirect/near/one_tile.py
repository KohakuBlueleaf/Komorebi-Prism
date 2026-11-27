"""The near and far fields as one product a screen tile, E = W_T . S_T: W_T from the
frame's geometry (the march's cells, the field lookup's groups, the ambient where no
lookup finds the field), S_T from the light (the cells' mean radiance, the groups' field
values, the ambient)."""

import numpy as np

from prism_reference.indirect.near.fuse import smooth
from prism_reference.indirect.near.pool import forked_map
from prism_reference.indirect.near.tile import PATTERN, cell_values, near_weights
from prism_reference.indirect.near.tile_far import (
    WIDTH,
    entry_places,
    far_columns,
    far_values,
    lookup_weights,
    product,
    tile_weights,
)

FORM = {**PATTERN, "tile": 16}


def far_band(model, places, covered, position, normal, tile, columns, y0):
    """The far columns of the band of tile rows from y0: W_far (rows, W, columns), the
    groups by (tile down, across), the lookups found (rows, W)."""
    rows = slice(y0, y0 + tile)
    cov, h, w = covered[rows], *covered[rows].shape
    entries = np.zeros((h, w, 24), np.int64)
    weights = np.zeros((h, w, 24))
    found = np.zeros((h, w), bool)
    entries[cov], weights[cov], found[cov] = lookup_weights(
        model, position[rows][cov], normal[rows][cov]
    )
    far, groups, _ = far_columns(entries, weights, cov, tile, columns, places=places)
    return far, {(y0 // tile, tx): g for (_, tx), g in groups.items()}, found


def tile_operator(
    op, frame, covered, position, normal, model, furnace, form=None, workers=1
):
    """W_T (H, W, WIDTH) of the frame the march ran on (`op`, `frame`; covered, world
    position and normal at its size) and what S_T needs: the far groups, the lookups
    found; K is the grouped lookup of the `furnace` field values over pi."""
    form = {**FORM, **(form or {})}
    tile = form["tile"]
    h, w = covered.shape
    near = near_weights(op, (h, w), tile, form)
    blocked = near.sum(-1)
    near, blocked = smooth([near, blocked], frame, op["rule"]["filter"], tile)
    columns = WIDTH - near.shape[-1] - 1
    inputs = (model, entry_places(model), covered, position, normal, tile, columns)
    done = forked_map(far_band, inputs, range(0, h, tile), workers)
    far = np.concatenate([d[0] for d in done])
    groups = {k: g for d in done for k, g in d[1].items()}
    found = np.concatenate([d[2] for d in done])
    k = product(far, far_values(groups, furnace, (h, w), tile, columns), tile)[..., 0]
    k = np.where(found, k / np.pi, 1.0)
    w_t, far_scale = tile_weights(near, blocked, far, k)
    missing = covered & ~found
    return {
        "w": np.concatenate([w_t, (far_scale * missing)[..., None]], -1),
        "far_scale": far_scale,
        "groups": groups,
        "found": found,
        "covered": covered,
        "columns": columns,
        "form": form,
    }


def tile_operand(t_op, radiance, behind, values, ambient):
    """S_T (tiles down, across, WIDTH, 3): the cells' mean of `radiance` (H, W, 3; and of
    `behind` for backface 2), the far groups of the field's `values`, the `ambient`."""
    form, covered = t_op["form"], t_op["covered"]
    near = cell_values(radiance, covered, form["tile"], form, behind)
    far = far_values(
        t_op["groups"], values, covered.shape, form["tile"], t_op["columns"]
    )
    last = np.broadcast_to(np.asarray(ambient, np.float64), near[:, :, :1].shape)
    return np.concatenate([near, far, last], 2)


def tile_light(t_op, operand):
    """E (H, W, 3) = W_T . S_T a tile."""
    return product(t_op["w"], operand, t_op["form"]["tile"])
