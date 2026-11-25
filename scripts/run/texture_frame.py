"""A shaded frame by the raster and texture classes alone on one card, stepped by the
host, against the reference's shaded frame: one JSON line, and the record written to
<out>/<scene>_<view>[_<W>_<H>]_frame.json. Example: python scripts/run/texture_frame.py
--scene sponza --view overview --size 1024 1024"""

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import komorebi as km

from prism.check import harness
from prism.stages.material.texture.check import frame
from prism_common.paths import data_root
from prism_reference.scene.camera import with_size
from prism_reference.scene.public.materials import load_materials
from prism_reference.scene.public.views import make_view

ROOT = Path(__file__).resolve().parents[2]
CORES = 120


def parse():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--scene", default="sponza")
    parser.add_argument("--view", default="overview", help="a public scene's view")
    parser.add_argument("--size", type=int, nargs=2, default=None, help="W H")
    parser.add_argument("--cores", type=int, default=CORES)
    parser.add_argument("--card", type=int, default=0)
    parser.add_argument(
        "--out", type=Path, default=ROOT / "measurements" / "texture_frame"
    )
    return parser.parse_args()


def main():
    args = parse()
    view = f"{args.scene}_{args.view}"
    scene = make_view(view, data_root())
    scene = scene if args.size is None else with_size(scene, args.size)
    materials = load_materials(view, data_root())[0]
    options = {"cores": args.cores, "size": args.size, "recount": False}
    name = "_".join([view, *map(str, args.size or []), "frame"])
    with km.Session(card=args.card) as session:
        loaded = SimpleNamespace(
            session=session,
            assembled=SimpleNamespace(pipeline=SimpleNamespace(name="texture_frame")),
        )

        def check(_):
            return frame.run(session, scene, materials, options)

        check.__qualname__ = check.__module__ = "texture_frame"
        record = harness.run(check, loaded, args.out / f"{name}.json")
    print(json.dumps(record, default=float), flush=True)


if __name__ == "__main__":
    main()
