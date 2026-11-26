"""Converts a glTF file into a scene of the tables (the mesh and materials files under the
data root, its entry in $PRISM_SCENES_EXTRA), or prints its coverage: convert | report.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from prism_common.paths import data_root
from prism_reference.scene.artist.convert import MOST_TRIANGLES, convert
from prism_reference.scene.description.report import coverage, text
from prism_reference.scene.importers import gltf
from prism_reference.scene.public.table import EXTRA_VARIABLE, TABLE


def extra_table():
    """The path $PRISM_SCENES_EXTRA names; an error saying to set it when unset."""
    value = os.environ.get(EXTRA_VARIABLE)
    if not value:
        raise SystemExit(
            f"${EXTRA_VARIABLE} is not set: name the JSON file the entry is added to"
        )
    return Path(value)


def run_convert(args):
    """Converts, writes the entry under the name and prints the report as JSON."""
    if args.name in json.loads(TABLE.read_text()):
        raise SystemExit(f"{args.name}: a public scene's name; choose another")
    extra = extra_table()
    started = time.perf_counter()
    entry, report = convert(
        args.file,
        args.name,
        args.data or data_root(),
        args.camera,
        args.most_triangles,
        args.licence,
        args.attribution,
        args.workers,
    )
    report["seconds"] = round(time.perf_counter() - started, 2)
    entries = json.loads(extra.read_text()) if extra.exists() else {}
    entries[args.name] = entry
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_text(json.dumps(entries, indent=1) + "\n")
    print(json.dumps({"name": args.name, "entry": entry} | report))


def main():
    """Converts a glTF file into a scene of the tables, or prints its coverage."""
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("command", choices=("convert", "report"))
    parser.add_argument("file", type=Path)
    parser.add_argument("--name", help="the scene's name in the table")
    parser.add_argument("--camera", help="the name of the view's camera node")
    parser.add_argument("--most-triangles", type=int, default=MOST_TRIANGLES)
    parser.add_argument("--licence", default="")
    parser.add_argument("--attribution", default="")
    parser.add_argument("--data", type=Path, default=None)
    parser.add_argument("--workers", type=int, default=4, help="texture decoders")
    args = parser.parse_args()
    if args.command == "report":
        print("\n".join(text(coverage(gltf.load(args.file)))))
        return 0
    if not args.name:
        parser.error("convert needs --name")
    run_convert(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
