"""The one-tile form's cases on the written scene, alone and blended (BAND): the white
furnace through W_T . S_T, W_T held while the sun moves against W_T built under the moved
sun, and the blend's seam: E's steps across the tiles' edges over those inside."""

import numpy as np

from checks.near_field import scene as written
from prism_reference.indirect.near.one_tile import (
    FORM,
    tile_light,
    tile_operand,
    tile_operator,
)
from prism_reference.scene.generated import uniform

SUNS = ((0.3, 0.8, 0.5), (-0.6, 0.5, 0.2))  # the sun before and after it moves
BAND = 4  # the blend's ramp half width in pixels
SEAM_MOST = 1.2  # the blended form's seam ratio at most
LUM = np.array([0.2126, 0.7152, 0.0722])
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


def seam_ratio(e, covered, frame, tile):
    """Mean |step| of E's luminance between neighbours of one surface (depth within 2 %,
    normals within 0.95) across the tiles' edges, over the same inside the tiles."""
    lum, n = e @ LUM, frame["normal"]
    z = np.where(covered, frame["depth"], 1.0)
    across, inside = [], []
    for axis in (0, 1):
        a = (
            (slice(None, -1), slice(None))
            if axis == 0
            else (slice(None), slice(None, -1))
        )
        b = (
            (slice(1, None), slice(None))
            if axis == 0
            else (slice(None), slice(1, None))
        )
        same = covered[a] & covered[b] & (np.abs(z[a] - z[b]) < 0.02 * np.abs(z[a]))
        same &= (n[a] * n[b]).sum(-1) > 0.95
        edge = np.arange(1, lum.shape[axis]) % tile == 0
        edge = np.broadcast_to(edge[:, None] if axis == 0 else edge[None], same.shape)
        step = np.abs(lum[b] - lum[a])
        across.append(step[same & edge])
        inside.append(step[same & ~edge])
    return float(np.concatenate(across).mean() / np.concatenate(inside).mean())


def form_cases(view, frame, op, model, furnace, form):
    """The furnace's worst |E / pi - 1|, the held W_T against the rebuilt one under the
    moved sun, and E under the moved sun, of the form `form`."""
    covered = view["covered"]
    args = (op, frame, covered, view["point"], view["normal"], model, furnace, form)
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
    out = {
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
    return out, moved


def cases(view, frame, op):
    """The form alone and blended: each one's furnace and held W_T; the seam ratio of
    each under the moved sun, the blended one's at most SEAM_MOST and under the other's.
    """
    model = field_model(view["point"], view["covered"])
    n = len(model["field_keys"]) * 6
    furnace = np.pi * (0.3 + 0.7 * uniform(np.arange(n), 0, 7))[:, None] * np.ones(3)
    alone, e_alone = form_cases(view, frame, op, model, furnace, {"band": 0})
    blended, e_blended = form_cases(view, frame, op, model, furnace, {"band": BAND})
    tile = FORM["tile"]
    seams = [seam_ratio(e, view["covered"], frame, tile) for e in (e_alone, e_blended)]
    return {
        **alone,
        **{f"blended_{k}": v for k, v in blended.items()},
        "blended_seam": {
            "band": BAND,
            "ratio_alone": seams[0],
            "ratio_blended": seams[1],
            "ok": seams[1] <= SEAM_MOST and seams[1] < seams[0],
        },
    }
