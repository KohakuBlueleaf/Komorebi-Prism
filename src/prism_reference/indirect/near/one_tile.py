"""The near and far fields as one product a screen tile, E = W_T . S_T: W_T from the
frame's geometry (the march's cells and the field lookup's groups), S_T from the light
(the cells' mean radiance and the groups' field values)."""

import numpy as np

from prism_reference.indirect.near.fuse import smooth
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


def tile_operator(op, frame, covered, position, normal, model, furnace, form=None):
    """W_T (H, W, WIDTH) of the frame the march ran on (`op`, `frame`; covered, world
    position and normal at its size) and what S_T needs: the far groups, the lookups
    found; K is the grouped lookup of the `furnace` field values over pi."""
    form = {**FORM, **(form or {})}
    tile = form["tile"]
    h, w = covered.shape
    near = near_weights(op, (h, w), tile, form)
    blocked = near.sum(-1)
    near, blocked = smooth([near, blocked], frame, op["rule"]["filter"], tile)
    entries = np.zeros((h, w, 24), np.int64)
    weights = np.zeros((h, w, 24))
    found = np.zeros((h, w), bool)
    entries[covered], weights[covered], found[covered] = lookup_weights(
        model, position[covered], normal[covered]
    )
    columns = WIDTH - near.shape[-1]
    far, groups, _ = far_columns(
        entries, weights, covered, tile, columns, places=entry_places(model)
    )
    k = product(far, far_values(groups, furnace, (h, w), tile, columns), tile)[..., 0]
    k = np.where(found, k / np.pi, 1.0)
    w_t, far_scale = tile_weights(near, blocked, far, k)
    return {
        "w": w_t,
        "far_scale": far_scale,
        "groups": groups,
        "found": found,
        "covered": covered,
        "columns": columns,
        "form": form,
    }


def tile_operand(t_op, radiance, behind, values):
    """S_T (tiles down, across, WIDTH, 3): the cells' mean of `radiance` (H, W, 3; and of
    `behind` for backface 2), then the far groups of the field's `values`."""
    form, covered = t_op["form"], t_op["covered"]
    near = cell_values(radiance, covered, form["tile"], form, behind)
    far = far_values(
        t_op["groups"], values, covered.shape, form["tile"], t_op["columns"]
    )
    return np.concatenate([near, far], 2)


def tile_light(t_op, operand, ambient):
    """E (H, W, 3) = W_T . S_T a tile, and the ambient where no lookup found the field."""
    e = product(t_op["w"], operand, t_op["form"]["tile"])
    missing = t_op["covered"] & ~t_op["found"]
    return e + (t_op["far_scale"] * missing)[..., None] * np.asarray(ambient)
