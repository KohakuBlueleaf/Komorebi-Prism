"""Real files: every `.glb` of a folder loaded, checked and reported against the counts
beside it; Khronos' Box against its known facts."""

import json
import resource
import time
from pathlib import Path

import numpy as np

from checks.scene_description.compare import RESULTS, same
from prism_reference.scene.description.check import check
from prism_reference.scene.description.report import coverage, text
from prism_reference.scene.importers.gltf import load

# report key: key of the counts file beside a scene
COUNTS = {
    "stored_triangles": "mesh_triangles",
    "materials": "materials",
    "images": "images",
    "cameras": "cameras",
    "punctual_lights": "lights",
    "file_instanced_nodes": "instanced_nodes",
}


def peak_mib():
    """The process's peak resident memory so far, in MiB."""
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)


def folder_case(folder, verbose):
    """Loads every `.glb` in `folder`, smallest first; returns one record a file."""
    records = []
    for path in sorted(Path(folder).glob("*.glb"), key=lambda p: p.stat().st_size):
        started = time.perf_counter()
        try:
            scene = load(path)
        except ValueError as error:
            RESULTS.append(
                {"case": f"{path.name} load", "equal": False, "got": str(error)}
            )
            records.append(
                {"file": path.name, "refused": str(error), "peak_mib": peak_mib()}
            )
            continue
        loaded = time.perf_counter() - started
        check(scene)
        report = coverage(scene)
        record = {
            "file": path.name,
            "bytes": path.stat().st_size,
            "load_s": round(loaded, 2),
            "check_s": round(time.perf_counter() - started - loaded, 2),
            "peak_mib": peak_mib(),
        }
        record |= {key: report[key] for key in COUNTS}
        record["instanced_nodes"] = report["instanced_nodes"]
        record["drawn_triangles"] = report["drawn_triangles"]
        beside = path.with_suffix(".json")
        if beside.is_file():
            counts = json.loads(beside.read_text())
            for key, theirs in COUNTS.items():
                same(f"{path.name} {key}", report[key], counts[theirs])
        if verbose:
            print("\n".join([f"== {path.name}"] + text(report)))
        records.append(record)
        del scene
    return records


def box_case(path):
    """Box.glb: 12 triangles, 24 vertices, bounds -0.5..0.5, its one material."""
    scene = load(path)
    check(scene)
    prims = [p for m in scene.meshes for p in m.primitives]
    same("box triangles", sum(len(p.indices) for p in prims), 12)
    same("box vertices", sum(len(p.positions) for p in prims), 24)
    positions = np.concatenate([p.positions for p in prims])
    same("box bounds low", positions.min(0), [-0.5, -0.5, -0.5])
    same("box bounds high", positions.max(0), [0.5, 0.5, 0.5])
    same("box materials", len(scene.materials), 1)
    m = scene.materials[0]
    same("box base colour", m.base_color, [0.8, 0.0, 0.0, 1.0])
    same("box metallic", m.metallic, 0.0)
