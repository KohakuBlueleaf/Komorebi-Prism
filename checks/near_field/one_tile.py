"""The one-tile form's cases on the written scene: the white furnace through W_T . S_T, and
W_T held while the sun moves against W_T built under the moved sun."""

import numpy as np

from checks.near_field import scene as written
from prism_reference.indirect.near.one_tile import (
    tile_light,
    tile_operand,
    tile_operator,
)
from prism_reference.scene.generated import uniform

SUNS = ((0.3, 0.8, 0.5), (-0.6, 0.5, 0.2))  # the sun before and after it moves
AXES = np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]])


def field_model(point, covered):
    """A field over the scene's box of points at the rule's spacing, every voxel kept with
    data on all six directions."""
    p = point[covered]
    origin = p.min(0) - 2 * written.SPACING
    dims = np.ceil((p.max(0) + 2 * written.SPACING - origin) / written.SPACING)
    dims = dims.astype(np.int64)
    n = int(np.prod(dims))
    return {
        "field_spacing": np.float32(written.SPACING),
        "field_origin": origin.astype(np.float32),
        "field_dims": dims,
        "field_keys": np.arange(n, dtype=np.int64),
        "field_has": np.ones((n, 6), bool),
    }


def sun_light(view, model, sun):
    """The sun's radiance a pixel (n . l, white surfaces) and a field value an entry
    (its direction's n . l, varied by the voxel's place), both (.., 3)."""
    lit = np.asarray(sun) / np.linalg.norm(sun)
    radiance = np.clip(view["normal"] @ lit, 0, None)[..., None] * np.ones(3)
    radiance *= view["covered"][..., None]
    n = len(model["field_keys"])
    vary = 0.5 + uniform(np.arange(n * 6), 0, 9).reshape(n, 6)
    values = np.clip(AXES @ lit, 0, None)[None] * vary
    return radiance, values.reshape(-1)[:, None] * np.ones(3)


def cases(view, frame, op):
    """The furnace's worst |E / pi - 1| and the held W_T against the rebuilt one under the
    moved sun (worst difference, and the sun's change of E)."""
    covered = view["covered"]
    model = field_model(view["point"], covered)
    n = len(model["field_keys"]) * 6
    furnace = np.pi * (0.3 + 0.7 * uniform(np.arange(n), 0, 7))[:, None] * np.ones(3)
    args = (op, frame, covered, view["point"], view["normal"], model, furnace)
    held = tile_operator(*args)
    ones = np.ones(covered.shape + (3,))
    e = tile_light(held, tile_operand(held, ones, ones, furnace, np.pi))
    worst = float(np.abs(e[covered] / np.pi - 1.0).max())
    behind = np.zeros_like(ones)
    radiance, values = sun_light(view, model, SUNS[0])
    before = tile_light(held, tile_operand(held, radiance, behind, values, 0.0))
    radiance, values = sun_light(view, model, SUNS[1])
    moved = tile_light(held, tile_operand(held, radiance, behind, values, 0.0))
    rebuilt = tile_operator(*args)
    again = tile_light(rebuilt, tile_operand(rebuilt, radiance, behind, values, 0.0))
    return {
        "furnace": {
            "pixels": int(covered.sum()),
            "worst": worst,
            "ok": worst < 1e-9,
        },
        "held_w_moved_sun": {
            "worst_against_rebuilt": float(np.abs(moved - again).max()),
            "sun_change": float(np.abs(moved - before).max()),
            "ok": bool(np.array_equal(moved, again) and (moved != before).any()),
        },
    }
