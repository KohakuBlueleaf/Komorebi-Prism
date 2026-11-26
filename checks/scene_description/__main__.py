"""Runs the scene description's check: round trips and refusals on files it writes, and on
request a folder of real files (`--files`) and Khronos' Box (`--box`); one JSON line."""

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

from checks.scene_description import build, files, refusals, roundtrip
from checks.scene_description.compare import RESULTS
from prism_common.paths import cache_root


def main():
    """Runs every case asked for; exit 1 when one differs."""
    parser = argparse.ArgumentParser(prog="python -m checks.scene_description")
    parser.add_argument(
        "--files", help="a folder of .glb files (with <name>.json counts)"
    )
    parser.add_argument("--box", help="the path of Khronos' Box.glb")
    parser.add_argument(
        "--verbose", action="store_true", help="print each file's report"
    )
    args = parser.parse_args()
    started = time.perf_counter()
    folder = tempfile.mkdtemp(prefix="scene_description_", dir=cache_root())
    summary = {}
    try:
        from_path = Path(folder)
        doc, writer, _ = build.document()
        glb, gltf = from_path / "quad.glb", from_path / "quad_text.gltf"
        build.write_glb(glb, doc, writer)
        build.write_gltf(gltf, doc, writer)
        roundtrip.file_case("glb", glb)
        roundtrip.file_case("gltf", gltf)
        roundtrip.sidecar_case("glb sidecar", glb)
        roundtrip.sidecar_case("gltf sidecar", gltf)
        refusals.run(from_path)
        if args.files:
            summary["files"] = files.folder_case(args.files, args.verbose)
        if args.box:
            files.box_case(args.box)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    different = [r for r in RESULTS if not r["equal"]]
    summary = {
        "ok": not different,
        "cases": len(RESULTS),
        "different": different,
    } | summary
    summary["peak_mib"] = files.peak_mib()
    summary["seconds"] = round(time.perf_counter() - started, 1)
    print(json.dumps(summary))
    return 1 if different else 0


if __name__ == "__main__":
    sys.exit(main())
