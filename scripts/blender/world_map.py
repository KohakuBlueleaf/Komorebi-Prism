"""Run inside Blender: the world's map of a sidecar as Radiance `.hdr` (the format the
reference reads), and the sidecar naming it.
`blender --background --python world_map.py -- <scene.prism.json> [--out <folder>]`
writes `<stem>.world.hdr` and the sidecar into --out (the sidecar's folder if none)."""

import argparse
import json
import os
import shutil
import sys

import bpy

HDR = ".hdr"


def save_hdr(image, path):
    """`image` (a loaded Blender image) saved as Radiance HDR at `path`, its pixels as
    they are (no view transform)."""
    own = image.file_format
    image.file_format = "HDR"
    try:
        image.save(filepath=path)
    finally:
        image.file_format = own


def world_hdr(source, folder, name):
    """The map at `source` as `<folder>/<name>`, Radiance HDR (a `.hdr` copied)."""
    path = os.path.join(folder, name)
    if os.path.splitext(source)[1].lower() == HDR:
        if os.path.abspath(source) != os.path.abspath(path):
            shutil.copyfile(source, path)
        return path
    image = bpy.data.images.load(source)
    save_hdr(image, path)
    bpy.data.images.remove(image)
    return path


def main():
    """Converts the sidecar's world map; one JSON line: the map and the sidecar."""
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("sidecar")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    here = os.path.dirname(os.path.abspath(args.sidecar))
    folder = args.out or here
    with open(args.sidecar) as f:
        entry = json.load(f)
    world = entry.get("world") or {}
    record = {"sidecar": None, "map": None}
    if world.get("environment"):
        source = os.path.join(here, world["environment"])
        stem = os.path.basename(args.sidecar).split(".")[0]
        path = world_hdr(source, folder, f"{stem}.world{HDR}")
        world["environment"] = os.path.basename(path)
        record["map"] = path
    out = os.path.join(folder, os.path.basename(args.sidecar))
    with open(out, "w") as f:
        f.write(json.dumps(entry, indent=1) + "\n")
    record["sidecar"] = out
    print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
