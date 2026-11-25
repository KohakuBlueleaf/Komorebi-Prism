"""A whole frame by the raster class alone on one card, stepped by the host, against the
reference: one JSON line, and the record written to
<out>/<scene>[_<view>][_<W>_<H>]_frame.json. Example: python scripts/run/raster_frame.py
--scene sponza --view overview"""

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import komorebi as km

from prism.check import harness
from prism.stages.raster.check import frame
from prism_common.paths import data_root
from prism_reference.scene.camera import with_size
from prism_reference.scene.generated import make_preset
from prism_reference.scene.public.views import make_view

ROOT = Path(__file__).resolve().parents[2]
CORES = 120


def parse():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--scene", default="tiny")
    parser.add_argument("--view", default=None, help="a public scene's view")
    parser.add_argument("--size", type=int, nargs=2, default=None, help="W H")
    parser.add_argument("--cores", type=int, default=CORES)
    parser.add_argument("--card", type=int, default=0)
    parser.add_argument(
        "--out", type=Path, default=ROOT / "measurements" / "raster_frame"
    )
    return parser.parse_args()


def scene_of(args):
    """The scene: a generated preset, or a public scene's view, at the size given."""
    scene = (
        make_preset(args.scene)
        if args.view is None
        else make_view(f"{args.scene}_{args.view}", data_root())
    )
    return scene if args.size is None else with_size(scene, args.size)


def main():
    args = parse()
    scene = scene_of(args)
    options = {"cores": args.cores, "size": args.size, "recount": False}
    name = "_".join(
        [args.scene, *([args.view] if args.view else []), *map(str, args.size or [])]
        + ["frame"]
    )
    with km.Session(card=args.card) as session:
        loaded = SimpleNamespace(
            session=session,
            assembled=SimpleNamespace(pipeline=SimpleNamespace(name="raster_frame")),
        )

        def check(_):
            return frame.run(session, scene, options)

        check.__qualname__ = check.__module__ = "raster_frame"
        record = harness.run(check, loaded, args.out / f"{name}.json")
    print(json.dumps(record, default=float), flush=True)


if __name__ == "__main__":
    main()
