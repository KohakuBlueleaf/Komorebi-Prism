"""The page of maps on the card: a walk at the viewer's speed (a tenth of the scene box's
diagonal a second at 60 frames a second, turning), the fitted maps kept while they hold
the eye's slices and drawn again beside the frames (a FIT command a map between two
frames, the records swapped in when whole); then frames standing (each frame whole or
stood, its kept lists),
each map the frames read against the reference's at its camera (texels over 1e-5
relative apart, texels empty on one side only), each map's levels against the
reference's of the card's map (exact); the redraws, the FIT and SUN commands' times and
the frames' seconds. One JSON line; the record to <out>/<scene>_<view>.json (out:
<cache root>/shadow_maps). Exit 1 on a frame's code or a map or level apart. Example:
python -m checks.shadow_maps --scene italian_flat_97f97a20ba --view camera --card 1"""

import argparse
import json
import math
import sys
import time
from pathlib import Path

import komorebi as km
import numpy as np
from prism_cli.preset import opened
from prism_viewer.server.camera import camera_of, diagonal, pose_of

from prism.check.threads import names
from prism.check.threads.card import recorded
from prism_common.paths import cache_root
from prism_reference.direct.shadow import map_at
from prism_reference.direct.shadow_filter import nearest_levels
from prism_reference.scene.camera import sized_camera

NAME = "direct.shadow_pcf"
FPS = 60
SPEED = 0.1  # of the scene box's diagonal a second (the viewer's walk)
TURN = 15.0  # degrees a second
STILL = 10  # frames standing after the walk (the last redraw among them)
RANGES = names.P + "ranges"  # a times row's count ranges (threads' presets)


def parse():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--pipeline", default="gi")
    parser.add_argument("--scene", default="italian_flat_97f97a20ba")
    parser.add_argument("--view", default="camera")
    parser.add_argument("--size", type=int, nargs=2, default=(1920, 1080))
    parser.add_argument("--card", type=int, required=True)
    parser.add_argument("--cascades", type=int, default=2)
    parser.add_argument("--margin", type=float, default=0.25)
    parser.add_argument("--seconds", type=float, default=2.0)
    parser.add_argument("--no-levels", action="store_true")
    parser.add_argument("--out", type=Path, default=None)
    return parser.parse_args()


def walk(scene, size, seconds):
    """The cameras at `size` of a walk ahead from the scene's camera, turning."""
    own = scene["camera"]
    first = pose_of(own)
    step = SPEED * diagonal(scene) / FPS
    out, pose = [], dict(first)
    for _ in range(int(seconds * FPS)):
        c, yaw = math.cos(pose["pitch"]), pose["yaw"]
        ahead = np.array(
            [c * math.sin(yaw), math.sin(pose["pitch"]), c * math.cos(yaw)]
        )
        position = np.add(pose["position"], ahead * step)
        pose = pose | {"position": [float(v) for v in position]}
        pose["yaw"] = yaw + math.radians(TURN / FPS)
        out.append(sized_camera(camera_of(own, pose), size))
    return out


def apart(got, want):
    """Texels over 1e-5 relative apart and texels empty on one side only."""
    with np.errstate(all="ignore"):
        relative = np.abs(got.astype(np.float64) - want) / np.abs(
            want.astype(np.float64)
        )
    both = (got > 0) & (want > 0)
    return {
        "apart": int((relative[both] > 1e-5).sum()),
        "empty_one_side": int(((got > 0) != (want > 0)).sum()),
    }


def judged(maps, scene, materials):
    """Each map against the reference's at its camera, its levels against the card
    map's."""
    out = []
    for one in maps:
        side = one["map"].shape[0]
        report = {"index": one["index"], "side": side}
        if one["index"]:
            want = map_at(scene, one["camera"], materials, side)
            report |= apart(one["map"], want)
        levels = one.get("levels") or []
        if levels:
            wanted = nearest_levels(one["map"])[1:]
            report["levels_apart"] = int(
                sum(
                    (a.view(np.uint32) != b.view(np.uint32)).sum()
                    for a, b in zip(levels, wanted, strict=True)
                )
            )
        out.append(report)
    return out


def main():
    args = parse()
    options = {
        "cascades": args.cascades,
        "cascade_margin": args.margin,
        "shadow_levels": not args.no_levels,
    }
    preset = opened(args.pipeline, args.scene, args.view, args.size, options)
    cameras = walk(preset.scene, preset.size, args.seconds)
    record = {"pipeline": args.pipeline, "scene": args.scene, "view": args.view}
    record |= {"size": list(preset.size)} | options
    with km.Session(card=args.card) as session:
        loop = preset.open(session)
        host = loop.loaded.hosts[NAME]
        frames = []
        try:
            for index, camera in enumerate(cameras + [cameras[-1]] * STILL):
                began = time.perf_counter()
                frame = loop.frame(camera)
                frames.append(
                    {
                        "code": frame.code,
                        "row": frame.row,
                        "s": round(time.perf_counter() - began, 4),
                        "asked": len(host.fits.asked),
                    }
                )
            maps = host.fitted_maps(loop.loaded)
        finally:
            loop.stop()
        times = host.times(loop.loaded)
        rows = loop.times()
    for one in frames:
        row = rows[one["row"]] if 0 <= one["row"] < len(rows) else None
        ranges = None if not row else row.get(RANGES)
        ranges = sum(ranges) if isinstance(ranges, list) else ranges
        one["kind"] = None if ranges is None else ("whole" if ranges else "tile")
    record["maps"] = judged(maps, preset.scene, loop.options["materials"])
    record["redraws"] = host.fits.redraws
    record["frames"] = frames
    record["passes"] = host.passes
    record["times"] = times
    codes = sorted({f["code"] for f in frames if f["code"]})
    bad = codes or any(
        m.get("apart") or m.get("empty_one_side") or m.get("levels_apart")
        for m in record["maps"]
    )
    fits = [t for t in times if t["map"] >= 0]
    summary = {
        "frames": len(frames),
        "codes": codes,
        "redraws": len(host.fits.redraws),
        "whole": sum(f["kind"] == "whole" for f in frames),
        "stood": sum(f["kind"] == "tile" for f in frames),
        "fit_us": [round(t["pass"], 1) for t in fits],
        "fit_view_us": [round(t["quadrants"][0], 1) for t in fits],
        "fit_levels_us": [round(t["levels"], 1) for t in fits],
        "fit_copies_us": [round(t["copies"], 1) for t in fits],
        "fit_ended": [t["ended"] for t in fits],
        "sun_us": [round(t["pass"], 1) for t in times if t["map"] < 0],
        "sun_levels_us": [round(t["levels"], 1) for t in times if t["map"] < 0],
        "sun_copies_us": [round(t["copies"], 1) for t in times if t["map"] < 0],
        "sun_ended": [t["ended"] for t in times if t["map"] < 0],
        "maps": record["maps"],
    }
    record["summary"] = summary
    stem = f"{args.scene}_{args.view}"
    recorded(record, (args.out or cache_root() / "shadow_maps") / f"{stem}.json")
    print(json.dumps(summary))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
