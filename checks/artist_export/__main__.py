"""Reads a folder's `scene.glb` JSON chunk, sidecar, instance table and `stats.json`, and
compares their counts, the triangles the sidecar records as not exported added back, and
finds the sidecar's render camera among its camera nodes; exit 1 on a difference."""

import json
import struct
import sys
from pathlib import Path

import numpy

GLB_MAGIC = 0x46546C67
JSON_CHUNK = 0x4E4F534A
TRIANGLES_MODE = 4


def gltf_document(path):
    """The JSON chunk of a .glb file."""
    with open(path, "rb") as f:
        magic, _, _ = struct.unpack("<III", f.read(12))
        length, kind = struct.unpack("<II", f.read(8))
        if magic != GLB_MAGIC or kind != JSON_CHUNK:
            raise ValueError(f"{path}: not a .glb with a JSON chunk first")
        return json.loads(f.read(length))


def mesh_triangles(document, mesh):
    """The triangles of a glTF mesh, over its primitives in triangle mode."""
    count = 0
    for primitive in document["meshes"][mesh]["primitives"]:
        if primitive.get("mode", TRIANGLES_MODE) != TRIANGLES_MODE:
            continue
        accessor = primitive.get("indices", primitive["attributes"]["POSITION"])
        count += document["accessors"][accessor]["count"] // 3
    return count


def main():
    """Checks the folder named on the command line."""
    folder = Path(sys.argv[1])
    document = gltf_document(folder / "scene.glb")
    sidecar = json.loads((folder / "scene.prism.json").read_text())
    stats = json.loads((folder / "stats.json").read_text())
    instances = numpy.load(folder / sidecar["instances"]["file"])
    names = [str(n) for n in instances["node_names"]]
    starts = instances["starts"]
    nodes = {n.get("name"): n for n in document.get("nodes", [])}
    missing = [n for n in names if "mesh" not in nodes.get(n, {})]
    recorded = {d["node"]: d for d in sidecar["not_exported"].get("triangles", [])}
    stored = drawn = 0
    unrecorded = []
    for i, name in enumerate(names):
        if name in missing:
            continue
        count = mesh_triangles(document, nodes[name]["mesh"])
        if name in recorded:
            if recorded[name]["written"] != count:
                unrecorded.append(name)
            count += recorded[name]["expected"] - recorded[name]["written"]
        stored += count
        drawn += count * int(starts[i + 1] - starts[i])
    area = len(sidecar["area_lights"])
    camera = sidecar["render"].get("camera")
    camera_found = camera is None or "camera" in nodes.get(camera, {})
    record = {
        "folder": folder.name,
        "nodes": len(names),
        "missing_nodes": missing[:20],
        "recorded_drops": len(recorded),
        "wrongly_recorded": unrecorded[:20],
        "stored_triangles": [stored, stats["stored_triangles"]],
        "drawn_triangles": [drawn, stats["drawn_triangles"]],
        "copies": [int(starts[-1]), stats["copies"]],
        "area_lights": [area, stats["lights"].get("AREA", 0)],
        "render_camera": [camera, camera_found],
        "version": sidecar["version"],
        "matrices": list(instances["matrices"].shape),
    }
    record["ok"] = (
        not missing
        and not unrecorded
        and stored == stats["stored_triangles"]
        and drawn == stats["drawn_triangles"]
        and area == stats["lights"].get("AREA", 0)
        and camera_found
        and sidecar["version"] == 1
        and len(starts) == len(names) + 1
        and int(starts[-1]) == len(instances["matrices"])
    )
    print(json.dumps(record))
    return 0 if record["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
