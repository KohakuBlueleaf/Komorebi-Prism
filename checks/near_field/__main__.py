"""Runs the near field's check (no card): the white furnace with the fusion on, and the
contact of a box on a floor against the field alone. One JSON line, exit 1 on a failure.
"""

import json
import sys
import time
from itertools import pairwise

import numpy as np

from checks.near_field import one_tile
from checks.near_field import scene as written
from prism_reference.indirect.near.fuse import (
    FLOOR_K,
    fused,
    near_frame,
    near_operator,
    near_radiance,
    smooth,
)
from prism_reference.scene.generated import uniform

BANDS = (0.0, 0.25, 0.5, 1.0, 1.5)  # floor distances from the box's face, in h
FAR = 3.5  # in h: past the near range and the filter
LOW_K_BAND = 0.5  # in h: the floor before the box has a field share under FLOOR_K


def furnace(view, frame, op):
    """Every source and the sky of radiance 1, the far field pi K with K drawn per pixel
    (under FLOOR_K at the contact): the fused E / pi at every receiver, and on the open
    floor with K under FLOOR_K."""
    covered = view["covered"]
    h, w = covered.shape
    k = 0.3 + 0.7 * uniform(np.arange(h * w), 0, 5).reshape(h, w).astype(np.float64)
    ahead = view["ahead"] / written.SPACING
    k[(ahead >= 0) & (ahead < LOW_K_BAND)] = 0.5 * FLOOR_K
    open_floor = ahead >= FAR
    ones = np.ones((h, w, 3))
    near = near_radiance(op, frame, ones)
    blocked = op["blocked"].reshape(h, w)
    near, blocked = smooth([near, blocked], frame, op["rule"]["filter"])
    e = fused(near, blocked, np.pi * k[..., None], k[..., None])
    low = np.full_like(k, 0.5 * FLOOR_K)[..., None]
    alone = fused(near, blocked, np.pi * low, low)[open_floor] / np.pi
    return e[covered] / np.pi, alone, low[open_floor]


def contact(view, frame, op):
    """A black box on a white floor under a white sky, the field alone reading 1: the
    fused E / pi of the floor in front of the box's face, a mean per band of distance.
    """
    h, w = view["covered"].shape
    radiance = np.where(view["floor"][..., None], 1.0, 0.0) * np.ones((1, 1, 3))
    near = near_radiance(op, frame, radiance, np.zeros_like(radiance))
    blocked = op["blocked"].reshape(h, w)
    near, blocked = smooth([near, blocked], frame, op["rule"]["filter"])
    ones = np.ones((h, w, 1))
    e = fused(near, blocked, np.pi * ones, ones)[..., 0] / np.pi
    ahead = view["ahead"] / written.SPACING
    bands = []
    for lo, hi in zip(BANDS, BANDS[1:] + (FAR,)):
        sel = (ahead >= lo) & (ahead < hi)
        bands.append((lo, int(sel.sum()), float(e[sel].mean()) if sel.any() else None))
    far = ahead >= FAR
    return bands, float(np.abs(e[far] - 1.0).max())


def main():
    """Builds the written frame and its near operator, then judges both cases."""
    started = time.perf_counter()
    view = written.frame()
    covered = view["covered"]
    n = view["normal"]
    frame = near_frame(view["camera"], view["point"], n, n, covered, 3)
    op = near_operator(frame, covered, written.SPACING)
    values, alone, low = furnace(view, frame, op)
    worst = float(np.abs(values - 1.0).max())
    fallback = float(np.abs(alone - low).max())
    bands, far = contact(view, frame, op)
    means = [b[2] for b in bands]
    filled = all(b[1] > 0 for b in bands)
    rising = filled and all(a < b for a, b in pairwise(means))
    darker = filled and means[0] < 0.85
    out = {
        "furnace": {
            "pixels": int(values.size // 3),
            "worst": worst,
            "ok": worst < 1e-9,
        },
        "low_share_without_hits": {
            "pixels": int(alone.size // 3),
            "reads_far_over_pi": fallback < 1e-12,
        },
        "contact": {
            "bands_h": [b[0] for b in bands],
            "pixels": [b[1] for b in bands],
            "mean": means,
            "far_worst": far,
            "rising": rising,
            "darker_than_field": darker,
            "ok": rising and darker and far < 1e-9,
        },
        "one_tile": one_tile.cases(view, frame, op),
        "seconds": round(time.perf_counter() - started, 2),
    }
    tiled = all(case["ok"] for case in out["one_tile"].values())
    out["ok"] = (
        out["furnace"]["ok"] and out["contact"]["ok"] and fallback < 1e-12 and tiled
    )
    print(json.dumps(out))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
