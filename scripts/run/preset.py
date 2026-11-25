"""A preset of configs/pipeline on one card: a Loop, its frames run by the thread and
checked by its last implementation's check; one JSON line, and the record written to
<out>/<scene>[_<view>]_<W>_<H>.json (out: measurements/<preset>_frame). --no-display: the
preset without its display (the implementations that fill `post`). Example: python
scripts/run/preset.py --pipeline textured --scene sponza --view overview --size 1024 1024
"""

import argparse
import ast
import importlib
import json
from pathlib import Path

import komorebi as km
from prism_cli.preset import opened

from prism.check import harness

ROOT = Path(__file__).resolve().parents[2]


def control(text):
    """NAME=VALUE as (name, a Python literal)."""
    name, _, value = text.partition("=")
    if not name or not _:
        raise argparse.ArgumentTypeError(f"{text!r} is not NAME=VALUE")
    return name, ast.literal_eval(value)


def parse():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--pipeline", default="raster", help="a preset's name")
    parser.add_argument("--scene", default="tiny")
    parser.add_argument("--view", default=None, help="a public scene's view")
    parser.add_argument("--size", type=int, nargs=2, default=None, help="W H")
    parser.add_argument("--frames", type=int, default=None, help="the preset's if none")
    parser.add_argument("--cores", type=int, default=None, help="every core if none")
    parser.add_argument("--card", type=int, default=0)
    parser.add_argument(
        "--no-display",
        action="store_true",
        help="the preset without the implementations that fill post",
    )
    parser.add_argument(
        "--set",
        type=control,
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="a control of the loop (<implementation>.<name>) set before the frames",
    )
    parser.add_argument(
        "--option",
        type=control,
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="an option of the preset given another value (bounces=0)",
    )
    parser.add_argument(
        "--check",
        default=None,
        metavar="MODULE.FUNCTION",
        help="the check run on the loop; the last implementation's if none",
    )
    parser.add_argument("--out", type=Path, default=None)
    return parser.parse_args()


def checked(path):
    """The check named by a dotted path (module.function), or None."""
    if path is None:
        return None
    module, _, name = path.rpartition(".")
    return getattr(importlib.import_module(module), name)


def main():
    args = parse()
    options = {"cores": args.cores}
    options |= dict(args.option)
    if args.frames is not None:
        options["frames"] = args.frames
    try:
        preset = opened(
            args.pipeline,
            args.scene,
            args.view,
            args.size,
            options,
            display=not args.no_display,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error
    pipeline, size = preset.pipeline, preset.size
    name = "_".join([args.scene, *([args.view] if args.view else []), *map(str, size)])
    with km.Session(card=args.card) as session:
        loop = preset.open(session)
        try:
            for control, value in args.set:
                loop.set(control, value)
            check = checked(args.check) or pipeline.implementations[-1].check
            out = args.out or ROOT / "measurements" / f"{args.pipeline}_frame"
            record = harness.run(check, loop, out / f"{name}.json")
        finally:
            loop.stop()
    print(json.dumps(record, default=float), flush=True)


if __name__ == "__main__":
    main()
