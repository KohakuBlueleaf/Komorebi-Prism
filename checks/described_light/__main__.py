"""Runs the direct light's check (no Blender, no card); one JSON line with `ok`, exit 1
on a difference."""

import json
import sys
import time

import numpy as np

from checks.described_light.scene import (
    EYE,
    cases,
    geometry,
    planes_of,
    written_scene,
)
from prism_reference.direct.described.direct import described_lights, direct_light
from prism_reference.trace.tree import build


def main():
    """Lights the written scene's floor points and compares each kind with its closed
    form: diffuse_light = E / pi."""
    started = time.perf_counter()
    found = cases()
    points = np.array([c[2] for c in found])
    planes = planes_of(points)
    tree = {k: np.ascontiguousarray(v) for k, v in build(geometry()).items()}
    lights, world, missing = described_lights(written_scene(), ".")
    out = direct_light(planes, EYE, tree, 40.0, lights, world)
    results = []
    for i, (kind, name, _, irradiance, share) in enumerate(found):
        got = out["kinds"][kind]["diffuse_light"][0, i].astype(np.float64)
        want = np.broadcast_to(np.asarray(irradiance, np.float64) / np.pi, (3,))
        error = np.abs(got - want)
        equal = bool(np.all(error <= share * np.abs(want) + 1e-9))
        entry = {"case": f"{kind}: {name}", "equal": equal}
        entry["got"], entry["want"] = float(got.mean()), float(want.mean())
        results.append(entry)
    different = [r for r in results if not r["equal"]]
    summary = {
        "ok": not different and not missing,
        "cases": len(results),
        "different": different,
        "not_carried": missing,
        "worst_area_share": max(
            abs(r["got"] - r["want"]) / r["want"]
            for r in results
            if r["case"].startswith("area")
        ),
        "rays": out["rays"],
        "seconds": round(time.perf_counter() - started, 2),
    }
    print(json.dumps(summary))
    return 1 if different or missing else 0


if __name__ == "__main__":
    sys.exit(main())
