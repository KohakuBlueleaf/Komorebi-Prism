"""Runs the shadow edge's check (no card): the filters, the PCSS radius, the cascade
and the traced share on a written scene against closed forms; with --view, every
option against the traced share on a scene's view. One JSON line, exit 1 on a failure.
"""

import argparse
import json
import sys
import time

import numpy as np

from checks.shadow_edge import scene as written
from checks.shadow_edge.measure import measure_view
from prism_reference.direct import shadow_cascade as cascade
from prism_reference.direct import shadow_filter as filters
from prism_reference.direct.shadow import sun_screen, sun_shadow
from prism_reference.direct.shadow_traced import caster_tree, traced_sun

RAYS = 256
METHODS = {
    "2x2": {"kind": "box", "width": 1},
    "box5": {"kind": "box", "width": 5},
    "pcss": {"kind": "pcss", "angle": written.ANGLE, "taps": 32},
    "pcss levels": {"kind": "pcss", "angle": written.ANGLE, "taps": 32, "levels": True},
}


def checks():
    """The written scene's results: {name: (passed, numbers)}."""
    view = written.scene()
    lights = written.lights(view)
    smap = filters.sun_map(lights)
    points, normals, pixels = written.floor_points(4000)
    truth = written.edge_share(points[:, 0])
    out = {}
    present = filters.filtered_shadow(smap, points, normals, METHODS["2x2"])
    same = sun_shadow(lights, points, normals)
    out["present filter unchanged"] = (bool(np.array_equal(present, same)), {})
    plain = written.materials(len(view["indices"]))
    tree, keep = caster_tree(view, plain)
    eps = float(view["eps"][0])
    angle, sun = written.ANGLE, lights["sun_direction"]
    traced = traced_sun(
        tree, keep, plain, points, normals, sun, angle, RAYS, eps, pixels
    )
    error = np.abs(traced - truth)
    numbers = {"mean": float(error.mean()), "worst": float(error.max())}
    out["traced share"] = (numbers["mean"] < 0.01 and numbers["worst"] < 0.05, numbers)
    sx, sy, w = sun_screen(smap["camera"], smap["texel"], points, normals)
    turn = filters.pixel_turn(pixels[:, 0], pixels[:, 1])
    plane = filters.receiver_plane(smap, normals, w)
    _, radius = filters.pcss(smap, sx, sy, w, angle, 32, turn, plane)
    penumbra = (truth > 0.05) & (truth < 0.95)
    reach = written.PLATE[0] / written.SUN[1]
    texel = (1 / w) / smap["camera"][12]
    want = reach * np.tan(angle / 2) / texel
    ratio = float(np.median(radius[penumbra] / want[penumbra]))
    out["pcss radius"] = (0.85 < ratio < 1.15, {"median ratio": ratio})
    mads = {
        name: float(
            np.abs(filters.filtered_shadow(smap, points, normals, m, pixels) - truth)[
                penumbra
            ].mean()
        )
        for name, m in METHODS.items()
    }
    fits = max(mads["pcss"], mads["pcss levels"]) < 0.5 * mads["2x2"]
    out["pcss fits the penumbra"] = (fits, mads)
    seen = (0.5, 12.0)
    maps = cascade.cascade_maps(view, None, lights, 2, 1024, seen)
    cam = view["camera"]
    near = (cam[0:3] + cam[9:12] * np.float32(1.0))[None]
    up = np.array([[0.0, 1.0, 0.0]], np.float32)
    choice = cascade.cascade_choice(maps, near, up, 4)
    texels = [float(m["texel"]) for m in maps]
    fine = texels[0] < texels[-1] and int(choice[0]) == 0
    sides = np.array([[5.0, 0, 0], [-5.0, 0, 0]], np.float32)
    lit, _ = cascade.cascade_shadow(maps, sides, np.repeat(up, 2, 0), METHODS["2x2"])
    numbers = {"texels": texels, "choice": int(choice[0]), "lit, shadow": lit.tolist()}
    out["cascade"] = (fine and lit.tolist() == [1.0, 0.0], numbers)
    reads = {name: filters.taps_of(m) for name, m in METHODS.items()}
    want = {"2x2": 4, "box5": 36, "pcss": 160, "pcss levels": 160}
    out["texel reads"] = (reads == want, reads)
    return out


def main():
    """The written scene's checks, then the view's measures when --view is given."""
    parser = argparse.ArgumentParser(prog="checks.shadow_edge")
    parser.add_argument("--view", default=None, help="a scene's view, as make_view")
    parser.add_argument("--rays", type=int, default=64)
    args = parser.parse_args()
    started = time.perf_counter()
    found = checks()
    failed = [name for name, (passed, _) in found.items() if not passed]
    summary = {
        "ok": not failed,
        "failed": failed,
        "checks": {name: numbers for name, (_, numbers) in found.items()},
    }
    if args.view:
        summary["view"] = measure_view(args.view, args.rays)
    summary["seconds"] = round(time.perf_counter() - started, 2)
    print(json.dumps(summary))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
