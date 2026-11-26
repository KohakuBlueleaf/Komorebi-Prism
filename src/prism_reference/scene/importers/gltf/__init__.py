"""glTF 2.0 (`.glb` and `.gltf`) into the scene description; a `<stem>.prism.json`
sidecar beside the file is applied when present."""

from pathlib import Path

import numpy as np

from prism_reference.scene.description.types import Mesh, Note, Primitive, Scene
from prism_reference.scene.importers.gltf import lights, materials, nodes, sidecar
from prism_reference.scene.importers.gltf.accessors import (
    floats,
    read,
    triangle_indices,
)
from prism_reference.scene.importers.gltf.container import open_container

REFUSED_REQUIRED = (
    "KHR_draco_mesh_compression",
    "EXT_meshopt_compression",
    "KHR_texture_basisu",
)
READ_REQUIRED = (
    "KHR_lights_punctual",
    "KHR_materials_emissive_strength",
    "KHR_texture_transform",
    "KHR_materials_unlit",
    "EXT_mesh_gpu_instancing",
)
NAMED = {
    "POSITION": "positions",
    "NORMAL": "normals",
    "TANGENT": "tangents",
    "TEXCOORD_0": "uv0",
    "TEXCOORD_1": "uv1",
}


def _colors(container, index):
    """COLOR_0 as (V, 4) float32, alpha 1 added to a VEC3."""
    colors = floats(container, index)
    if colors.shape[1] == 3:
        colors = np.concatenate([colors, np.ones((len(colors), 1), np.float32)], 1)
    return colors


def _primitive(container, entry):
    """The Primitive of one triangle primitive."""
    attributes = entry["attributes"]
    values = {
        NAMED[k]: floats(container, a) for k, a in attributes.items() if k in NAMED
    }
    positions = values.pop("positions")
    if "indices" in entry:
        indices = triangle_indices(container, entry["indices"])
    else:
        if len(positions) % 3:
            raise ValueError(f"unindexed primitive: {len(positions)} vertices")
        indices = np.arange(len(positions), dtype=np.uint32).reshape(-1, 3)
    prim = Primitive(positions, indices, material=entry.get("material", -1), **values)
    if "COLOR_0" in attributes:
        prim.colors = _colors(container, attributes["COLOR_0"])
    for key, index in attributes.items():
        if key not in NAMED and key != "COLOR_0":
            prim.carried[key] = read(container, index)
    if "targets" in entry:
        prim.carried["targets"] = [
            {k: read(container, a) for k, a in target.items()}
            for target in entry["targets"]
        ]
    return prim


def _meshes(container):
    """Every mesh's triangle primitives; other modes dropped and noted."""
    found, dropped, carried, count = [], {}, 0, 0
    for mesh in container.doc.get("meshes", []):
        out = Mesh(name=mesh.get("name", ""))
        for entry in mesh["primitives"]:
            mode = entry.get("mode", 4)
            if mode != 4:
                dropped[mode] = dropped.get(mode, 0) + 1
                continue
            out.primitives.append(_primitive(container, entry))
            carried += bool(out.primitives[-1].carried)
            count += 1
        found.append(out)
    notes = [Note("used", "meshes", len(found)), Note("used", "primitives", count)]
    if carried:
        notes.append(Note("carried", "primitive joints, weights or targets", carried))
    for mode, n in sorted(dropped.items()):
        notes.append(Note("dropped", f"primitive mode {mode}", n))
    return found, notes


def _required(doc):
    """ValueError for a refused required extension; notes for others not read."""
    notes = []
    for name in doc.get("extensionsRequired", []):
        if name in REFUSED_REQUIRED:
            raise ValueError(f"required extension {name}: not supported")
        if name not in READ_REQUIRED:
            notes.append(Note("refused", name, 1, "required by the file, not read"))
    return notes


def _file_counts(doc):
    """Counts over the whole file, every scene: scenes, nodes, instanced nodes."""
    entries = doc.get("nodes", [])
    return {
        "scenes": len(doc.get("scenes", [])),
        "nodes": len(entries),
        "instanced_nodes": sum(
            "EXT_mesh_gpu_instancing" in n.get("extensions", {}) for n in entries
        ),
    }


def load(path) -> Scene:
    """The Scene of a glTF file, its sidecar applied when one lies beside it."""
    container = open_container(path)
    doc = container.doc
    source = {"path": str(path), "format": container.format, "bytes": container.bytes}
    scene = Scene(source=source | {"file": _file_counts(doc)})
    scene.notes.extend(_required(doc))
    scene.meshes, notes = _meshes(container)
    scene.notes.extend(notes)
    found = materials.materials(container)
    scene.materials, scene.textures, scene.samplers, scene.images, notes = found
    scene.notes.extend(notes)
    scene.lights, scene.cameras, notes = lights.lights_and_cameras(doc)
    scene.notes.extend(notes)
    scene.nodes, notes = nodes.nodes(container)
    scene.notes.extend(notes)
    scene.animations = list(doc.get("animations", []))
    scene.skins = list(doc.get("skins", []))
    for what, items in (("animations", scene.animations), ("skins", scene.skins)):
        if items:
            scene.notes.append(Note("carried", what, len(items)))
    side = sidecar.sidecar_path(path)
    if Path(side).is_file():
        sidecar.apply(scene, side)
    return scene
