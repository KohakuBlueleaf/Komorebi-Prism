"""Runs the surface's check (no Blender, no card); one JSON line with `ok`, exit 1 on a
difference."""

import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

from checks.surface import record
from checks.surface.filtering import filter_cases
from checks.surface.model import brdf_cases, tangent_cases
from checks.surface.scene import surface_case
from prism_common.paths import cache_root


def main():
    """Runs every case."""
    started = time.perf_counter()
    off_normal = brdf_cases()
    filter_cases()
    tangent_cases()
    folder = Path(tempfile.mkdtemp(prefix="surface_", dir=cache_root()))
    try:
        surface_case(folder)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    different = [r for r in record.RESULTS if not r["equal"]]
    summary = {
        "ok": not different,
        "cases": len(record.RESULTS),
        "different": different,
    }
    summary["furnace_off_normal"] = off_normal
    summary["seconds"] = round(time.perf_counter() - started, 2)
    print(json.dumps(summary))
    return 1 if different else 0


if __name__ == "__main__":
    sys.exit(main())
