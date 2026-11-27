"""The 2 x 2 taps' keys of `prism.stages.direct.shadow_pcf.model.share` (the twin of
kernels/share.hpp), no card: on points spread over each scene's triangles, the form
from a point through the sun's map against the reference's taps (prism_reference.direct
.access: tap_texels, tap_pages) key for key; then, the lamps' faces of the scene (when
it has lamp shapes) or the sun's quadrants, each point given one of them, the form from
each lane's own map coordinates against the form through each map alone. One JSON line;
exit 1 on a key apart. Example: python -m checks.shadow_share --scenes sponza
italian_flat_97f97a20ba"""

import argparse
import json
import sys

import numpy as np

from prism.stages.direct.shadow_pcf.model.region import quadrant_cameras
from prism.stages.direct.shadow_pcf.model.share import (
    PAGE,
    PAGE_SHIFT,
    coordinate_taps,
    point_taps,
    project,
)
from prism_common.paths import data_root
from prism_reference.direct.access import NONE, tap_pages, tap_texels
from prism_reference.direct.lamp_maps import lamp_faces
from prism_reference.direct.lights import load as load_lights
from prism_reference.direct.lights import shadow_side
from prism_reference.scene.public.table import table
from prism_reference.scene.public.views import make_view

F = np.float32
POINTS = 200_000


def parse():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--scenes", nargs="+", default=["sponza"])
    parser.add_argument("--points", type=int, default=POINTS)
    parser.add_argument("--file-lights", action="store_true", help="the file's lamps")
    parser.add_argument("--seed", type=int, default=1)
    return parser.parse_args()


def surface_points(view, count, rng):
    """`count` points on the view's triangles (area-weighted) and their unit normals."""
    p = view["positions"][view["indices"]].astype(np.float64)
    cross = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    area = np.linalg.norm(cross, axis=1)
    keep = area > 0
    p, cross, area = p[keep], cross[keep], area[keep]
    tri = rng.choice(len(p), count, p=area / area.sum())
    u, v = rng.random(count), rng.random(count)
    flip = u + v > 1
    u, v = np.where(flip, 1 - u, u), np.where(flip, 1 - v, v)
    point = p[tri, 0] + u[:, None] * (p[tri, 1] - p[tri, 0])
    point += v[:, None] * (p[tri, 2] - p[tri, 0])
    normal = cross[tri] / area[tri, None]
    return point.astype(F), normal.astype(F)


def reference_keys(lights, points, normals):
    """The reference's 2 x 2 taps as keys (1 + page) << 10 | texel, 0 outside."""
    side = shadow_side(lights)
    sized = {**lights, "shadow_map": np.zeros((side, side), F)}
    taps = tap_texels(sized, points, normals)
    pages = tap_pages(sized, taps, 1)
    texel = (taps[..., 1] % PAGE) * PAGE + taps[..., 0] % PAGE
    key = (pages << PAGE_SHIFT) | texel
    return np.where(pages == NONE, 0, key).astype(np.uint32)


def maps_of(lights):
    """The maps each lane may take: the lamps' faces, else the sun's quadrants (their
    cameras, widths, heights, first pages + 1 laid one after another)."""
    faces = lamp_faces(lights)
    if faces:
        cameras = [f["camera"] for f in faces]
        sizes = [tuple(int(v) for v in f["size"]) for f in faces]
    else:
        side = shadow_side(lights)
        cameras = quadrant_cameras(lights)
        quarter = side // int(np.sqrt(len(cameras)))
        sizes = [(quarter, quarter)] * len(cameras)
    firsts, first = [], 1
    for width, height in sizes:
        firsts.append(first)
        first += (width // PAGE) * (height // PAGE)
    return cameras, sizes, firsts


def scene_report(name, args, rng):
    """One scene's keys apart: the sun's form against the reference, the lanes' form
    against each map's alone."""
    view_name = f"{name}_{next(iter(table()[name]['views']))}"
    view = make_view(view_name, data_root())
    lights = load_lights(name, data_root(), args.file_lights, False)
    points, normals = surface_points(view, args.points, rng)
    side = shadow_side(lights)
    across = side // PAGE
    keys, _, _, _ = point_taps(
        points,
        normals,
        lights["shadow_camera"],
        lights["shadow_texel"],
        1,
        across,
        side,
        side,
    )
    want = reference_keys(lights, points, normals)
    out = {
        "points": len(points),
        "sun_keys_inside": int((want != 0).sum()),
        "sun_keys_apart": int((keys != want).sum()),
    }
    cameras, sizes, firsts = maps_of(lights)
    pick = rng.integers(0, len(cameras), len(points))
    sx, sy = np.zeros(len(points), F), np.zeros(len(points), F)
    alone = np.zeros((len(points), 4), np.uint32)
    texel = F(0.0)
    for index, (camera, (width, height), first) in enumerate(
        zip(cameras, sizes, firsts, strict=True)
    ):
        lanes = pick == index
        if not lanes.any():
            continue
        x, y, _ = project(points[lanes], normals[lanes], camera, texel)
        sx[lanes], sy[lanes] = x, y
        alone[lanes], _, _, _ = point_taps(
            points[lanes],
            normals[lanes],
            camera,
            texel,
            first,
            width // PAGE,
            width,
            height,
        )
    widths = np.array([w for w, _ in sizes])[pick]
    heights = np.array([h for _, h in sizes])[pick]
    firsts = np.array(firsts)[pick]
    lane_keys, _, _ = coordinate_taps(sx, sy, firsts, widths // PAGE, widths, heights)
    out |= {
        "maps": len(cameras),
        "maps_kind": "faces" if lamp_faces(lights) else "quadrants",
        "lane_keys_inside": int((alone != 0).sum()),
        "lane_keys_apart": int((lane_keys != alone).sum()),
    }
    return out


def main():
    args = parse()
    rng = np.random.default_rng(args.seed)
    record = {name: scene_report(name, args, rng) for name in args.scenes}
    apart = sum(r["sun_keys_apart"] + r["lane_keys_apart"] for r in record.values())
    print(json.dumps({"ok": apart == 0, "scenes": record}))
    return 0 if apart == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
