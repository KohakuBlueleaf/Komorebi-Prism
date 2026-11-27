"""The threads' form checked: `model` (no card) the checks' own parts against the model;
`tile` the tile pull alone on the model's data, `depth` the sun's DEPTH view alone (a map
of one quadrant: --shadow-side) against the stage-wise map, `geometry` count, sums and
place against the model, `whole` the threads' preset's frame (with lights: the sun set,
its command sent, its map compared too), `update` the field's update (its field against
the stage-wise update's at each --deal) and the frames after it, `during` the frames
while it runs (each the field before or after it); each against the
stage-wise preset `--pipeline`, at each of `--cores` and `--policy`. One JSON line; the
record to <out>/<part>_<scene>[_<view>]_<W>_<H>.json (out: measurements/threads_frame).
Exit 1 on a difference. Example: python -m checks.threads_frame tile --pipeline textured
--scene <scene> --view <view> --card 1"""

import argparse
import json
import sys
from pathlib import Path

import komorebi as km
from prism_cli.preset import opened

from checks.raster_model.compare import RESULTS
from checks.threads_frame import model_only
from prism.check.threads import (
    depth_half,
    during,
    geometry_half,
    names,
    tile_half,
    update,
    whole,
)
from prism.check.threads.card import recorded
from prism_reference.direct.lights import sun_angles
from prism_reference.scene.camera import with_size

ROOT = Path(__file__).resolve().parents[2]
PARTS = ("model", "tile", "depth", "geometry", "whole", "update", "during")
SUFFIX = "_threads"  # the threads' preset of a stage-wise preset


def cores_of(text):
    """A count of cores, or 'all' (None: every core)."""
    return None if text == "all" else int(text)


def parse():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("part", choices=PARTS)
    parser.add_argument("--pipeline", default="textured", help="a stage-wise preset")
    parser.add_argument("--scene", default="tiny")
    parser.add_argument("--view", default=None, help="a public scene's view")
    parser.add_argument("--size", type=int, nargs=2, default=None, help="W H")
    parser.add_argument(
        "--cores", type=cores_of, nargs="+", default=[1, None], help="counts or all"
    )
    parser.add_argument(
        "--policy", nargs="+", choices=sorted(names.POLICIES), default=None
    )
    parser.add_argument(
        "--heavy", type=int, default=None, help="the threads' tiles cut past it"
    )
    parser.add_argument(
        "--deadline", type=float, default=None, help="seconds a command may take"
    )
    parser.add_argument(
        "--sun",
        type=float,
        nargs=2,
        default=None,
        help="azimuth elevation (depth, whole)",
    )
    parser.add_argument(
        "--no-sun", action="store_true", help="whole: no sun set, its map as it stands"
    )
    parser.add_argument(
        "--shadow-side", type=int, default=None, help="the map's side (depth, whole)"
    )
    parser.add_argument(
        "--no-recover", action="store_true", help="a core that gives up stays as it is"
    )
    parser.add_argument(
        "--deal",
        type=cores_of,
        nargs="+",
        default=None,
        help="update: the stage-wise transport's cores (else the update's, then all)",
    )
    parser.add_argument(
        "--bounces", type=int, default=None, help="the field's passes (with a sun)"
    )
    parser.add_argument(
        "--frames", type=int, default=64, help="during: frames sent at most"
    )
    parser.add_argument("--card", type=int, default=None, help="needed but for model")
    parser.add_argument("--out", type=Path, default=None)
    return parser.parse_args()


def opener(args, session):
    """open_loop(preset, options): the preset's Loop for the scene on `session` (a
    threads' preset's as a stage-wise one's)."""

    def open_loop(name, options):
        given = {key: value for key, value in options.items() if value is not None}
        return opened(name, args.scene, args.view, args.size, given).open(session)

    return open_loop


def sun_of(args):
    """The whole part's sun options: the sun set (--sun, else the lights' own) when
    the scene has lights, so both loops send its command; {} without lights or with
    --no-sun (the lights' map as it stands)."""
    if args.lights is None or args.no_sun:
        return {}
    sun = tuple(args.sun) if args.sun else sun_angles(args.lights["sun_direction"])
    given = {"sun": tuple(float(angle) for angle in sun)}
    if args.bounces is not None:
        given |= {"bounces": args.bounces}
    if args.shadow_side is not None:
        given |= {"shadow_side": args.shadow_side}
        given |= {"lights": depth_half.lights_of(args.lights, args.shadow_side)}
    return given


def on_card(args, scene):
    """The card part's record."""
    threads_name = args.pipeline + SUFFIX
    policies = args.policy or list(names.POLICIES)
    options = {"heavy": args.heavy, "deadline": args.deadline}
    options |= {"recover": False if args.no_recover else None}
    with km.Session(card=args.card) as session:
        open_loop = opener(args, session)
        match args.part:
            case "tile":
                return tile_half.check(
                    open_loop,
                    threads_name,
                    args.pipeline,
                    scene,
                    args.cores,
                    policies,
                    options,
                )
            case "depth":
                sun = {"sun": args.sun and tuple(args.sun)}
                sun |= {"shadow_side": args.shadow_side}
                sun |= {"lights": depth_half.lights_of(args.lights, args.shadow_side)}
                given = {k: v for k, v in (options | sun).items() if v is not None}
                return depth_half.check(
                    open_loop,
                    threads_name,
                    args.pipeline,
                    scene,
                    args.cores,
                    policies,
                    given,
                )
            case "update":
                return update.check(
                    open_loop,
                    threads_name,
                    args.pipeline,
                    scene,
                    policies,
                    options,
                    sun_of(args),
                    args.deal or [None],
                )
            case "during":
                return during.check(
                    open_loop,
                    threads_name,
                    args.pipeline,
                    scene,
                    policies[0],
                    options,
                    sun_of(args),
                    args.frames,
                    None,
                )
            case "geometry":
                return geometry_half.check(
                    open_loop, threads_name, scene, args.cores, options
                )
            case _:
                return whole.check(
                    open_loop,
                    threads_name,
                    args.pipeline,
                    scene,
                    args.cores,
                    policies,
                    options,
                    sun_of(args),
                )


def main():
    args = parse()
    try:
        preset = opened(args.pipeline, args.scene, args.view, args.size)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    scene = with_size(preset.scene, preset.size)
    name = "_".join(
        [args.scene, *([args.view] if args.view else []), *map(str, preset.size)]
    )
    if args.part == "model":
        model_only.codes_case()
        model_only.log_case()
        model_only.run(name, scene, preset.options)
        different = [r["case"] for r in RESULTS if not r["equal"]]
        print(json.dumps({"cases": len(RESULTS), "different": different}))
        return 1 if different else 0
    if args.card is None:
        raise SystemExit(f"{args.part}: --card names the card")
    args.lights = preset.options.get("lights")
    record = on_card(args, scene)
    record |= {"part": args.part, "pipeline": args.pipeline, "scene": name}
    out = args.out or ROOT / "measurements" / "threads_frame"
    recorded(record, out / f"{args.part}_{name}.json")
    print(json.dumps({k: record[k] for k in ("part", "scene", "equal") if k in record}))
    return 0 if record.get("equal") else 1


if __name__ == "__main__":
    sys.exit(main())
