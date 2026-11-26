"""Lists, fetches and converts the public scenes, and writes their materials, lights and
indirect files under the data root: list | fetch | materials | lighting | indirect."""

import argparse
import json
import os
from pathlib import Path

from prism_common.paths import data_root
from prism_reference.direct.prepare import prepare
from prism_reference.indirect.build import build
from prism_reference.scene.files import checksum, export_npy, save_scene
from prism_reference.scene.public.materials import convert_materials, load_materials
from prism_reference.scene.public.mesh import convert, load_mesh
from prism_reference.scene.public.table import table
from prism_reference.scene.public.views import make_view

MOST_WORKERS = 32


def main():
    """Lists, fetches and converts the public scenes."""
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument(
        "command", choices=("list", "fetch", "materials", "lighting", "indirect")
    )
    parser.add_argument("scenes", nargs="*")
    parser.add_argument("--data", type=Path, default=None)
    parser.add_argument(
        "--workers",
        type=int,
        default=min(len(os.sched_getaffinity(0)), MOST_WORKERS),
        help="processes (the CPUs it may run on, at most 32, if none)",
    )
    parser.add_argument("--rebake", action="store_true", help="trace visibility again")
    parser.add_argument(
        "--visibility",
        choices=("open", "bake"),
        default="bake",
        help="lighting: the sky's visibility baked, or 1 a vertex until baked",
    )
    args = parser.parse_args()
    data = args.data or data_root()
    if args.command == "lighting":
        for name in args.scenes or [n for n, e in table().items() if "lighting" in e]:
            out, counts = prepare(
                name, data, args.workers, args.rebake, visibility=args.visibility
            )
            print(f"{name}: {out} {counts}")
        return
    if args.command == "indirect":
        for name in args.scenes:
            print(f"{name}: {json.dumps(build(name, data))}")
        return
    if args.command == "list":
        for name, entry in table().items():
            print(f"{name}: {', '.join(entry['views'])} - {entry['attribution']}")
        return
    if args.command == "materials":
        for name in args.scenes or [n for n, e in table().items() if "materials" in e]:
            out = convert_materials(name, data, args.workers)
            _, counts = load_materials(name, data)
            print(f"{name}: {out} {counts}")
        return
    for name in args.scenes or list(table()):
        out = convert(name, data)
        _, counts = load_mesh(name, data)
        print(f"{name}: {out} {counts}")
        for view in table()[name]["views"]:
            scene = make_view(f"{name}_{view}", data)
            folder = Path(data) / f"{name}_{view}"
            save_scene(Path(data) / f"{name}_{view}.npz", scene)
            export_npy(scene, folder)
            print(f"  {name}_{view}: sha256 {checksum(scene)}")


if __name__ == "__main__":
    main()
