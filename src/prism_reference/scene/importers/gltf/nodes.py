"""The node hierarchy of a glTF file's default scene: local and world matrices, `moving`,
and EXT_mesh_gpu_instancing composed into world transforms."""

import numpy as np

from prism_reference.scene.description.types import Node, Note
from prism_reference.scene.importers.gltf.accessors import floats


def rotations(q):
    """(N, 3, 3) rotation matrices of (N, 4) unit quaternions (x, y, z, w)."""
    q = np.asarray(q, np.float64).reshape(-1, 4)
    x, y, z, w = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    out = np.empty((len(q), 3, 3))
    out[:, 0] = np.stack(
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], 1
    )
    out[:, 1] = np.stack(
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], 1
    )
    out[:, 2] = np.stack(
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)], 1
    )
    return out


def compose(translation, rotation, scale):
    """(N, 4, 4) matrices T @ R @ S from (N, 3) translations, (N, 4) quaternions, (N, 3)."""
    count = len(translation)
    out = np.zeros((count, 4, 4))
    out[:, :3, :3] = rotations(rotation) * np.asarray(scale, np.float64)[:, None, :]
    out[:, :3, 3] = translation
    out[:, 3, 3] = 1.0
    return out


def local_matrix(entry):
    """A node's local matrix: its `matrix` (column-major in the file) or T @ R @ S."""
    if "matrix" in entry:
        return np.array(entry["matrix"], np.float64).reshape(4, 4).T
    return compose(
        [entry.get("translation", [0.0, 0.0, 0.0])],
        [entry.get("rotation", [0.0, 0.0, 0.0, 1.0])],
        [entry.get("scale", [1.0, 1.0, 1.0])],
    )[0]


def scene_order(doc):
    """The file's node indices in the default scene, each parent before its children."""
    scenes = doc.get("scenes", [])
    if not scenes:
        return list(range(len(doc.get("nodes", []))))
    roots = scenes[doc.get("scene", 0)].get("nodes", [])
    order, parent_of = [], {}
    stack = [(r, -1) for r in reversed(roots)]
    while stack:
        index, parent = stack.pop()
        if index in parent_of:
            raise ValueError(f"node {index}: reached twice in the scene's tree")
        parent_of[index] = parent
        order.append(index)
        children = doc["nodes"][index].get("children", [])
        stack.extend((c, index) for c in reversed(children))
    return order


def _instances(container, extension, world):
    """(N, 4, 4) float32 world transforms of the copies EXT_mesh_gpu_instancing names."""
    attributes = extension.get("attributes", {})
    counts = [container.doc["accessors"][a]["count"] for a in attributes.values()]
    if not counts:
        return None
    count = counts[0]
    t = np.zeros((count, 3))
    r = np.tile([0.0, 0.0, 0.0, 1.0], (count, 1))
    s = np.ones((count, 3))
    if "TRANSLATION" in attributes:
        t = floats(container, attributes["TRANSLATION"])
    if "ROTATION" in attributes:
        r = floats(container, attributes["ROTATION"])
    if "SCALE" in attributes:
        s = floats(container, attributes["SCALE"])
    return (world @ compose(t, r, s)).astype(np.float32)


def nodes(container):
    """The default scene's nodes, each parent before its children, and the notes."""
    doc = container.doc
    entries = doc.get("nodes", [])
    order = scene_order(doc)
    new = {old: i for i, old in enumerate(order)}
    targets = {
        c["target"]["node"]
        for a in doc.get("animations", [])
        for c in a.get("channels", [])
        if "node" in c.get("target", {})
    }
    found, instanced = [], 0
    for old in order:
        entry = entries[old]
        node = Node(name=entry.get("name", ""))
        node.mesh = entry.get("mesh", -1)
        node.camera = entry.get("camera", -1)
        light = entry.get("extensions", {}).get("KHR_lights_punctual", {})
        node.light = light.get("light", -1)
        node.local = local_matrix(entry)
        found.append(node)
    for old in order:
        for child in entries[old].get("children", []):
            if child in new:
                found[new[child]].parent = new[old]
    for i, old in enumerate(order):
        node, entry = found[i], entries[old]
        above = found[node.parent] if node.parent != -1 else None
        node.world = node.local if above is None else above.world @ node.local
        node.moving = old in targets or "skin" in entry or bool(above and above.moving)
        extension = entry.get("extensions", {}).get("EXT_mesh_gpu_instancing")
        if extension is not None:
            node.instances = _instances(container, extension, node.world)
            instanced += node.instances is not None
    notes = [Note("used", "nodes", len(found))]
    notes.append(Note("computed", "node world matrices", len(found)))
    if instanced:
        notes.append(Note("used", "EXT_mesh_gpu_instancing", instanced))
    if len(entries) > len(found):
        notes.append(
            Note(
                "dropped", "nodes outside the default scene", len(entries) - len(found)
            )
        )
    return found, notes
