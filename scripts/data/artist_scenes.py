"""Lists and fetches the artists' scenes, and runs the scripts of `scripts/blender/` on
them into <data>/artist/<key>/: list | fetch | measure | export | render | planes |
gltf_truth (Cycles and EEVEE of the exported .glb read back by Blender's importer);
selftest runs the material rewrite's own check in Blender."""

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

from prism_common.paths import cache_root, data_root
from prism_reference.scene.artist.table import (
    artist_dir,
    attribution,
    blend_path,
    download,
    table,
    unpack,
)

BLENDER_VARIABLE = "PRISM_BLENDER"
SCRIPTS = Path(__file__).resolve().parent.parent / "blender"
PAUSE_SECONDS = 20
ENGINE_STEMS = {"CYCLES": "truth", "EEVEE": "eevee"}
GLTF_STEMS = {"CYCLES": "truth_gltf", "EEVEE": "eevee_gltf"}
GLTF_BLEND = "scene_gltf.blend"  # the .glb and its sidecar as a scene of their own
PLANES = "surface/cycles.npz"  # the planes of truth.exr, under a scene's folder


def blender(key, data, script, arguments, timeout, open_blend=True):
    """Runs a script of `scripts/blender/` on a scene (without opening a .blend when
    `open_blend` is False, on another .blend when it is a path); its JSON line, or the
    failure."""
    opened = open_blend if isinstance(open_blend, Path) else blend_path(key, data)
    command = [
        os.environ.get(BLENDER_VARIABLE, "blender"),
        "--background",
        "--disable-autoexec",
        *([str(opened)] if open_blend else []),
        "--python",
        str(SCRIPTS / f"{script}.py"),
        "--",
        *arguments,
    ]
    try:
        done = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired:
        return {"error": f"stopped after {timeout} s"}
    lines = [ln[ln.find('{"') :] for ln in done.stdout.splitlines() if '{"' in ln]
    if done.returncode or not lines:
        tail = (done.stdout + done.stderr).strip().splitlines()[-3:]
        return {"error": f"exit {done.returncode}", "tail": tail}
    return json.loads(lines[-1])


def selftest(timeout):
    """The material rewrite's check, run in Blender on an empty file; its JSON line."""
    command = [
        os.environ.get(BLENDER_VARIABLE, "blender"),
        "--background",
        "--factory-startup",
        "--python",
        str(SCRIPTS / "selftest_materials.py"),
    ]
    try:
        done = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired:
        return {"error": f"stopped after {timeout} s"}
    lines = [ln for ln in done.stdout.splitlines() if ln.startswith('{"')]
    if done.returncode or not lines:
        tail = (done.stdout + done.stderr).strip().splitlines()[-3:]
        return {"error": f"exit {done.returncode}", "tail": tail}
    return json.loads(lines[-1])


def fetch(keys, data):
    """Downloads (checked) and unpacks each scene, 20 s between two downloads."""
    fetched = False
    for key in keys:
        if fetched:
            time.sleep(PAUSE_SECONDS)
        fetched = download(key, data)
        unpack(key, data)
        print(json.dumps({"scene": key, "downloaded": fetched}), flush=True)


def renders(key, data, args, stems, opened=True):
    """{engine: render.py's JSON line} of each engine of `args` into `stems`."""
    folder = artist_dir(data) / key
    frame = ["--frame", str(args.frame)] if args.frame is not None else []
    record = {}
    for engine in args.engines:
        arguments = [
            str(folder / stems[engine]),
            "--engine",
            engine,
            "--size",
            *map(str, args.size),
            "--samples",
            str(args.samples),
            *frame,
        ]
        record[engine] = blender(key, data, "render", arguments, args.timeout, opened)
    return record


def run(command, keys, data, args):
    """Runs measure, export, render, planes or gltf_truth on each scene; one JSON line
    a scene."""
    for key in keys:
        folder = artist_dir(data) / key
        folder.mkdir(exist_ok=True)
        frame = ["--frame", str(args.frame)] if args.frame is not None else []
        record = {"scene": key}
        if command == "measure":
            arguments = [str(folder / "stats.json")]
            record |= blender(key, data, "measure", arguments, args.timeout)
        elif command == "export":
            bakes = cache_root() / "bakes" / key
            arguments = [str(folder / "scene"), *frame, "--cache", str(bakes)]
            arguments += ["--plain"] * args.plain
            record |= blender(key, data, "export", arguments, args.timeout)
        elif command == "planes":
            (folder / PLANES).parent.mkdir(exist_ok=True)
            arguments = [str(folder / "truth.exr"), str(folder / PLANES)]
            record |= blender(key, data, "planes", arguments, args.timeout, False)
        elif command == "gltf_truth":
            arguments = [str(folder / "scene"), str(folder / GLTF_BLEND)]
            record["build"] = blender(
                key, data, "from_gltf", arguments, args.timeout, False
            )
            if "error" not in record["build"]:
                record |= renders(key, data, args, GLTF_STEMS, folder / GLTF_BLEND)
        else:
            record |= renders(key, data, args, ENGINE_STEMS)
        print(json.dumps(record), flush=True)


def main():
    """Lists, fetches, measures, exports and renders the artists' scenes."""
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument(
        "command",
        choices=(
            "list",
            "fetch",
            "measure",
            "export",
            "render",
            "planes",
            "gltf_truth",
            "selftest",
        ),
    )
    parser.add_argument("scenes", nargs="*")
    parser.add_argument("--data", type=Path, default=None)
    parser.add_argument("--frame", type=int, default=None)
    parser.add_argument("--plain", action="store_true", help="export: no rewrite")
    parser.add_argument("--size", type=int, nargs=2, default=(1280, 720))
    parser.add_argument("--samples", type=int, default=256)
    parser.add_argument(
        "--engines", nargs="+", choices=tuple(ENGINE_STEMS), default=["CYCLES", "EEVEE"]
    )
    parser.add_argument("--timeout", type=float, default=None, help="seconds a run")
    args = parser.parse_args()
    data = args.data or data_root()
    keys = args.scenes or list(table())
    if args.command == "selftest":
        record = selftest(args.timeout)
        print(json.dumps(record), flush=True)
        raise SystemExit(0 if record.get("ok") else 1)
    if args.command == "list":
        for key in keys:
            print(f"{key}: {attribution(key)}")
    elif args.command == "fetch":
        fetch(keys, data)
    else:
        run(args.command, keys, data, args)


if __name__ == "__main__":
    main()
