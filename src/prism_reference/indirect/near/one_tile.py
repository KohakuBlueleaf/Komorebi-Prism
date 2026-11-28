"""The near and far fields as one product a screen tile, E = W_T . S_T: W_T from the
frame's geometry (the march's cells, the field lookup's groups, the ambient where no
lookup finds the field), S_T from the light (the cells' mean radiance, the groups' field
values, the ambient)."""

import numpy as np

from prism_reference.indirect.near.blend import blended_product, blended_rows
from prism_reference.indirect.near.fuse import smooth
from prism_reference.indirect.near.pool import forked_map
from prism_reference.indirect.near.tile import (
    PATTERN,
    cell_values,
    near_weights,
    pattern_cells,
)
from prism_reference.indirect.near.tile_far import (
    WIDTH,
    entry_places,
    far_columns,
    far_values,
    lookup_weights,
    product,
    tile_weights,
)

# The tile in pixels; the blend's ramp half width in pixels (0: each pixel its tile's).
FORM = {**PATTERN, "tile": 16, "band": 4}


def far_band(model, places, covered, position, normal, tile, columns, y0):
    """The far columns of the band of tile rows from y0: W_far (rows, W, columns), the
    groups by (tile down, across), the lookups found (rows, W), their entries and
    weights (rows, W, 24)."""
    rows = slice(y0, y0 + tile)
    cov, h, w = covered[rows], *covered[rows].shape
    entries = np.zeros((h, w, 24), np.int64)
    weights = np.zeros((h, w, 24))
    found = np.zeros((h, w), bool)
    entries[cov], weights[cov], found[cov] = lookup_weights(
        model, position[rows][cov], normal[rows][cov]
    )
    far, groups, _ = far_columns(entries, weights, cov, tile, columns, places=places)
    groups = {(y0 // tile, tx): g for (_, tx), g in groups.items()}
    return far, groups, found, entries, weights


def tile_operator(
    op, frame, covered, position, normal, model, furnace, form=None, workers=1
):
    """W_T (H, W, WIDTH; with a band (H, W, 4, WIDTH) and the class tiles) of the frame
    the march ran on (`op`, `frame`; covered, position and normal at its size) and what
    S_T needs: the far groups, the lookups found; K the grouped `furnace` lookup / pi.
    """
    form = {**FORM, **(form or {})}
    tile = form["tile"]
    h, w = covered.shape
    cells = len(pattern_cells(tile, form["split"], form["rings"]))
    columns = WIDTH - cells * (2 if form["backface"] == 2 else 1) - 1
    places = entry_places(model)
    inputs = (model, places, covered, position, normal, tile, columns)
    done = forked_map(far_band, inputs, range(0, h, tile), workers)
    far, found, entries, weights = (
        np.concatenate([d[i] for d in done]) for i in (0, 2, 3, 4)
    )
    groups = {k: g for d in done for k, g in d[1].items()}
    k_values = far_values(groups, furnace, (h, w), tile, columns)
    out = {
        "groups": groups,
        "found": found,
        "covered": covered,
        "columns": columns,
        "form": form,
    }
    if form["band"] > 0:
        lookups = (entries, weights, found, covered, places)
        w_b, owners = blended_rows(op, frame, lookups, groups, k_values, form)
        return {**out, "w": w_b, "owners": owners}
    near = near_weights(op, (h, w), tile, form)
    blocked = near.sum(-1)
    near, blocked = smooth([near, blocked], frame, op["rule"]["filter"], tile)
    k = product(far, k_values, tile)[..., 0]
    k = np.where(found, k / np.pi, 1.0)
    w_t, far_scale = tile_weights(near, blocked, far, k)
    missing = covered & ~found
    return {**out, "w": np.concatenate([w_t, (far_scale * missing)[..., None]], -1)}


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
    """E (H, W, 3) = W_T . S_T a tile (with a band: summed over the class tiles)."""
    if "owners" in t_op:
        return blended_product(t_op["w"], t_op["owners"], operand)
    return product(t_op["w"], operand, t_op["form"]["tile"])
