"""The eye's lists kept while its view stands: a sequence of frames (stand, stand, the sun
moved, stand, stand, a control set, stand, the pose moved, stand, a smaller size, stand,
a larger size, stand, a reload, stand) on the threads' preset as it loads, and again with keep_lists
off (every frame counted and placed); each frame's kind (`tile`: no count range ran,
`whole`) against the kind the sequence asks for, each picture against the other load's
byte for byte. One JSON line; the record to <out>/<preset>_<scene>_<view>.json (out:
<cache root>/lists_kept). Exit 1 on a code, a kind or a picture that differs. Example:
python -m checks.lists_kept --scene sponza --view overview --card 1"""

import argparse
import json
import math
import sys
from pathlib import Path

import komorebi as km
from prism_cli.preset import opened
from prism_viewer.server.camera import camera_of, pose_of

from prism.check.threads import compare, names
from prism.check.threads.card import recorded
from prism_common.paths import cache_root
from prism_reference.scene.camera import sized_camera

TURN = 15.0  # degrees the pose turns
SUN_TURN = 30.0  # degrees the sun's azimuth turns
GAMMA_STEP = 0.2  # the control's change
RANGES = names.P + "ranges"  # a times row's count ranges


def parse():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--pipeline", default="gi_threads", help="a threads' preset")
    parser.add_argument("--scene", default="sponza")
    parser.add_argument("--view", default="overview")
    parser.add_argument("--size", type=int, nargs=2, default=(1920, 1080))
    parser.add_argument("--card", type=int, required=True)
    parser.add_argument("--out", type=Path, default=None)
    return parser.parse_args()


def control(loop, suffix):
    """The loop's control named `<implementation>.<suffix>`, or None."""
    for one in loop.controls():
        if one.name.endswith("." + suffix):
            return one
    return None


def sun_turned(loop):
    """The sun's azimuth turned by SUN_TURN; False when the preset has no sun."""
    sun = control(loop, "sun")
    if sun is None:
        return False
    azimuth, elevation = sun.value
    loop.set(sun.name, ((azimuth + SUN_TURN) % 360.0, elevation))
    return True


def gamma_changed(loop):
    """The display's gamma moved by GAMMA_STEP within its limits; False when none."""
    gamma = control(loop, "gamma")
    if gamma is None:
        return False
    low, high = gamma.limits
    value = gamma.value + GAMMA_STEP
    loop.set(gamma.name, value if value <= high else max(low, gamma.value - GAMMA_STEP))
    return True


def updated(loop):
    """The field's update the sun started waited for and taken, beside the frames or
    as a command: the frames after it read the new field in both loads."""
    loop.collect(wait=True)
    for host in loop.hosts():
        graph = getattr(host, "graph", None)
        if graph is not None and graph.handle is not None:
            graph.served(wait=True)


def reloaded(loop):
    """The pipeline loaded again at the capacity held."""
    loop.reload(loop.held, "check")
    return True


def steps(scene, size):
    """[(what, camera, size)] of the sequence: what happens before the frame."""
    own = scene["camera"]
    turned = camera_of(
        own, pose_of(own) | {"yaw": pose_of(own)["yaw"] + math.radians(TURN)}
    )
    small = (size[0] // 2, size[1] // 2)
    large = (size[0] + size[0] // 4, size[1] + size[1] // 4)
    plan = [
        ("load", own, size),
        ("stand", own, size),
        ("sun", own, size),
        ("stand", own, size),
        ("stand", own, size),
        ("control", own, size),
        ("stand", own, size),
        ("pose", turned, size),
        ("stand", turned, size),
        ("smaller", turned, small),
        ("stand", turned, small),
        ("larger", turned, large),
        ("stand", turned, large),
        ("reload", turned, large),
        ("stand", turned, large),
    ]
    return [(what, sized_camera(camera, at), at) for what, camera, at in plan]


def played(loop, plan):
    """Each step of `plan` on `loop`: its record and its picture; the kinds from the
    times rows once stopped."""
    out, pictures = [], []
    for what, camera, at in plan:
        done = {"sun": sun_turned, "control": gamma_changed, "reload": reloaded}.get(
            what
        )
        happened = done(loop) if done else True
        if tuple(at) != loop.size:
            loop.resize(at)
        reloads, live = len(loop.reloads), len(loop.recoveries)
        frame = loop.frame(camera, picture=True)
        out.append(
            {
                "what": what if happened else f"{what} (none)",
                "code": frame.code,
                "row": frame.row,
                "reloads": len(loop.reloads) - reloads,
                "recoveries": len(loop.recoveries) - live,
            }
        )
        pictures.append(frame.picture)
        if what == "sun":
            updated(loop)
    loop.stop()
    rows = loop.times()
    for one in out:
        row = rows[one["row"]] if 0 <= one["row"] < len(rows) else None
        ranges = None if not row else row.get(RANGES)
        ranges = sum(ranges) if isinstance(ranges, list) else ranges
        one["kind"] = None if ranges is None else ("whole" if ranges else "tile")
    return out, pictures


def asked(one):
    """The kind a step asks for: the tile alone only for a frame whose view stood and
    that took no reload or live recovery."""
    stood = one["what"].split(" ")[0] in ("stand", "control")
    return "tile" if stood and not one["reloads"] and not one["recoveries"] else "whole"


def main():
    args = parse()
    record = {"pipeline": args.pipeline, "scene": args.scene, "view": args.view}
    with km.Session(card=args.card) as session:
        runs = {}
        for name, keep in (("whole", False), ("kept", True)):
            preset = opened(
                args.pipeline, args.scene, args.view, args.size, {"keep_lists": keep}
            )
            loop = preset.open(session)
            runs[name] = played(loop, steps(preset.scene, preset.size))
    (wanted, want), (frames, got) = runs["whole"], runs["kept"]
    for one, other, picture, against in zip(frames, wanted, got, want, strict=True):
        one["asked"] = asked(one)
        one["whole_kind"] = other["kind"]
        if picture is None or against is None:
            one["equal"] = False
            continue
        judged = compare.pictures(picture, against)
        one["equal"] = judged["equal"]
        if not judged["equal"]:
            one["picture"] = {k: v for k, v in judged.items() if k != "equal"}
    record["frames"] = frames
    record["codes"] = sorted({o["code"] for o in frames + wanted if o["code"]})
    record["kinds"] = [o["kind"] for o in frames]
    record["wrong_kind"] = [
        i
        for i, o in enumerate(frames)
        if o["kind"] != o["asked"] or o["whole_kind"] != "whole"
    ]
    record["differ"] = [i for i, o in enumerate(frames) if not o["equal"]]
    stem = "_".join([args.pipeline, args.scene, args.view or ""])
    recorded(record, (args.out or cache_root() / "lists_kept") / f"{stem}.json")
    summary = ("kinds", "codes", "wrong_kind", "differ")
    print(json.dumps({k: record[k] for k in summary}))
    return 1 if record["codes"] or record["wrong_kind"] or record["differ"] else 0


if __name__ == "__main__":
    sys.exit(main())
