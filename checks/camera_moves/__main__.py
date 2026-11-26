"""Camera moves that leave the load's view (turns, looks up and down, a walk through the
scene, by the viewer's pose math) on a preset loaded once: each frame's code, its
recoveries (reloads with their code by name and seconds, live recoveries with what
they changed and their milliseconds) and its seconds; with --against, each picture
against the stage-wise preset's of the same camera, byte for byte. One JSON line; the
record to <out>/<preset>_<scene>_<view>_<W>_<H>.json (out: <cache root>/camera_moves).
Exit 1 on a reload, a frame that ends with a code, or a differing picture. Example:
python -m checks.camera_moves --pipeline gi_threads --against gi --scene sponza
--view overview --size 1920 1080 --card 1"""

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

import prism.program.threads.host as threads_host
import prism.stages.raster.host as raster_host
from prism.check.threads import compare
from prism.check.threads.card import recorded
from prism_common.paths import cache_root
from prism_reference.scene.camera import sized_camera

TURN = 15.0  # degrees a frame of a turn
LOOK = 20.0  # degrees a frame of a look up or down
WALK = 0.01  # of the scene box's diagonal a frame of a walk
CODE_NAMES = {
    value: name for name, value in (raster_host.CODES | threads_host.CODES).items()
}


def parse():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--pipeline", default="gi_threads", help="the preset moved")
    parser.add_argument("--against", default=None, help="a stage-wise preset")
    parser.add_argument("--scene", default="sponza")
    parser.add_argument("--view", default="overview")
    parser.add_argument("--size", type=int, nargs=2, default=(1920, 1080))
    parser.add_argument("--card", type=int, required=True)
    parser.add_argument(
        "--sun",
        type=float,
        nargs=3,
        default=None,
        metavar=("FRAME", "AZIMUTH", "ELEVATION"),
        help="the sun moved before that frame (the field's update then runs)",
    )
    parser.add_argument("--out", type=Path, default=None)
    return parser.parse_args()


def ahead(pose):
    """The pose's view direction (the viewer's)."""
    c, yaw = math.cos(pose["pitch"]), pose["yaw"]
    return np.array([c * math.sin(yaw), math.sin(pose["pitch"]), c * math.cos(yaw)])


def right(pose):
    """The pose's right (the viewer's)."""
    return np.array([-math.cos(pose["yaw"]), 0.0, math.sin(pose["yaw"])])


def moved(pose, **change):
    """`pose` with `change`; a position as a list."""
    out = dict(pose) | change
    out["position"] = [float(v) for v in out["position"]]
    return out


def looks(out, pose, first):
    """Looks up and down from `pose` appended to `out`: the pose after, level as
    `first`."""
    for pitch in (1, 2, 3, 4, 3, 2, 1, 0, -1, -2, -3, -4, -3, -2, -1, 0):
        pose = moved(pose, pitch=first["pitch"] + math.radians(LOOK) * pitch)
        out.append(("look", pose))
    return pose


def moves(first, size):
    """(path, pose) of every frame: a turn, looks, a walk ahead, a turn there, looks,
    a walk to the right, looks, a walk back to the view's own place."""
    out = [("view", dict(first))]
    pose = dict(first)
    for _ in range(int(360 / TURN)):
        pose = moved(pose, yaw=pose["yaw"] + math.radians(TURN))
        out.append(("turn", pose))
    pose = looks(out, pose, first)
    step = WALK * size
    for _ in range(30):
        pose = moved(pose, position=np.add(pose["position"], ahead(pose) * step))
        out.append(("walk", pose))
    for _ in range(12):
        pose = moved(pose, yaw=pose["yaw"] + math.radians(2 * TURN))
        out.append(("turn there", pose))
    pose = looks(out, pose, first)
    for _ in range(15):
        pose = moved(pose, position=np.add(pose["position"], right(pose) * step))
        out.append(("walk right", pose))
    pose = looks(out, pose, first)
    back = np.subtract(first["position"], pose["position"]) / 15
    for _ in range(15):
        pose = moved(pose, position=np.add(pose["position"], back))
        out.append(("walk back", pose))
    return out


def cameras(scene, size):
    """(path, camera at `size`) of every frame of moves()."""
    own = scene["camera"]
    first = pose_of(own)
    return [
        (path, sized_camera(own if index == 0 else camera_of(own, pose), size))
        for index, (path, pose) in enumerate(moves(first, diagonal(scene)))
    ]


def code_of(why):
    """A reload's code by name from its why ("code N"), else the why."""
    if why.startswith("code "):
        code = int(why.split()[1])
        return CODE_NAMES.get(code, str(code))
    return why


def sun_moved(loop, sun):
    """The loop's sun control (`<implementation>.sun`) set to `sun` (azimuth,
    elevation)."""
    names = [c.name for c in loop.controls() if c.name.endswith(".sun")]
    if not names:
        raise SystemExit("--sun: the preset has no sun control")
    loop.set(names[0], tuple(sun))


def updating(loop):
    """Whether a host's update (its graph) runs beside the frames now."""
    graphs = [getattr(host, "graph", None) for host in loop.hosts()]
    return any(getattr(graph, "handle", None) is not None for graph in graphs)


def played(loop, frames, pictures, sun=None):
    """Each frame of `frames` on `loop` (`sun`: (frame, azimuth, elevation), the sun
    moved before that frame): its record; its picture kept when `pictures`."""
    out, kept = [], []
    for index, (path, camera) in enumerate(frames):
        if sun is not None and index == int(sun[0]):
            sun_moved(loop, sun[1:])
        reloads = len(loop.reloads)
        live = len(getattr(loop, "recoveries", []))
        began = time.perf_counter()
        frame = loop.frame(camera, picture=pictures)
        one = {
            "frame": index,
            "path": path,
            "code": CODE_NAMES.get(frame.code, frame.code) if frame.code else 0,
            "s": round(time.perf_counter() - began, 3),
            "reloads": [
                {"code": code_of(r["why"]), "s": r["s"]} for r in loop.reloads[reloads:]
            ],
            "recoveries": list(getattr(loop, "recoveries", [])[live:]),
            "update": updating(loop),
        }
        out.append(one)
        kept.append(frame.picture)
        if one["reloads"] or one["recoveries"] or frame.code:
            print(json.dumps(one), file=sys.stderr, flush=True)
    return out, kept


def run(args, name, frames, pictures, session):
    """The preset `name` opened, `frames` played, stopped: (records, pictures,
    seconds of the open)."""
    began = time.perf_counter()
    preset = opened(name, args.scene, args.view, args.size)
    loop = preset.open(session)
    opened_s = round(time.perf_counter() - began, 3)
    try:
        records, kept = played(loop, frames, pictures, args.sun)
    finally:
        loop.stop()
    return records, kept, opened_s


def main():
    args = parse()
    preset = opened(args.pipeline, args.scene, args.view, args.size)
    frames = cameras(preset.scene, preset.size)
    record = {"pipeline": args.pipeline, "against": args.against}
    record |= {"scene": args.scene, "view": args.view, "size": list(preset.size)}
    with km.Session(card=args.card) as session:
        want = None
        if args.against:
            _, want, _ = run(args, args.against, frames, True, session)
        records, got, record["open_s"] = run(
            args, args.pipeline, frames, bool(want), session
        )
    if want is not None:
        for one, picture, other in zip(records, got, want, strict=True):
            if picture is None or other is None:
                one["equal"] = False
                continue
            judged = compare.pictures(picture, other)
            one["equal"] = judged["equal"]
            if not judged["equal"]:
                one["picture"] = {k: v for k, v in judged.items() if k != "equal"}
    record["frames"] = records
    reloads = [r for one in records for r in one["reloads"]]
    live = [r for one in records for r in one["recoveries"]]
    record["reloads"], record["recoveries"] = len(reloads), len(live)
    record["reload_s"] = round(sum(r["s"] for r in reloads), 3)
    record["recovery_ms"] = round(sum(r.get("ms", 0.0) for r in live), 3)
    record["update_frames"] = [one["frame"] for one in records if one["update"]]
    record["codes"] = sorted({one["code"] for one in records if one["code"]})
    if want is not None:
        record["differ"] = [one["frame"] for one in records if not one["equal"]]
    bad = record["reloads"] or record["codes"] or record.get("differ")
    stem = "_".join(
        [args.pipeline, args.scene, args.view or "", *map(str, preset.size)]
    )
    recorded(record, (args.out or cache_root() / "camera_moves") / f"{stem}.json")
    summary = ("reloads", "reload_s", "recoveries", "recovery_ms", "codes", "differ")
    print(json.dumps({k: record[k] for k in summary if k in record}))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
