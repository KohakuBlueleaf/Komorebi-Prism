"""Runs the glTF scene conversion's check on a file it writes under $PRISM_CACHE; one JSON
line with `ok`, exit 1 on a difference."""

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from checks.gltf_scene import cases, opened, scene
from checks.gltf_scene.blocks import blocks_cases
from prism_common.paths import DATA_VARIABLE, cache_root
from prism_reference.scene.artist.convert import convert
from prism_reference.scene.public.materials import load_materials
from prism_reference.scene.public.table import EXTRA_VARIABLE

NAME = "gltf_check"
PLAIN = "gltf_plain"


def main():
    """Writes the file, converts it, runs every case."""
    started = time.perf_counter()
    folder = Path(tempfile.mkdtemp(prefix="gltf_scene_", dir=cache_root()))
    previous = os.environ.get(EXTRA_VARIABLE)
    try:
        path = folder / "check.glb"
        scene.write(path)
        data = folder / "data"
        entry, report = convert(path, NAME, data, workers=1)
        extra = folder / "extra_scenes.json"
        extra.write_text(json.dumps({NAME: entry}))
        os.environ[EXTRA_VARIABLE] = str(extra)
        materials = cases.files_case(NAME, data)
        cases.kinds_case(materials, report)
        cases.corners_case(load_materials(NAME, data)[0])
        cases.view_case(NAME, data)
        cases.entry_case(entry)
        blocks_cases(NAME, data, folder)
        plain = folder / "plain.glb"
        scene.write_plain(plain)
        convert(plain, PLAIN, data, workers=1)
        cases.untextured_case(PLAIN, data)
        opened.opened_cases(folder, os.environ.get(DATA_VARIABLE))
    finally:
        if previous is None:
            os.environ.pop(EXTRA_VARIABLE, None)
        else:
            os.environ[EXTRA_VARIABLE] = previous
        shutil.rmtree(folder, ignore_errors=True)
    different = [r for r in cases.RESULTS if not r["equal"]]
    summary = {"ok": not different, "cases": len(cases.RESULTS), "different": different}
    summary["seconds"] = round(time.perf_counter() - started, 2)
    print(json.dumps(summary))
    return 1 if different else 0


if __name__ == "__main__":
    sys.exit(main())
