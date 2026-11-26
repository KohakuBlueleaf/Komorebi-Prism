"""The `<stem>.prism.json` sidecar beside a scene file and its instance table: world,
render settings, area lights, instances and what the exporter did not write."""

import json
from pathlib import Path

import numpy as np

from prism_reference.scene.description.types import Light, Node, Note, Render, World

VERSION = 1
NOT_EXPORTED = (("materials", "material"), ("lights", "light"), ("objects", "object"))


def sidecar_path(path):
    """The sidecar's path for a scene file: `<stem>.prism.json` beside it."""
    path = Path(path)
    return path.with_name(path.stem + ".prism.json")


def _node_index(scene, name, what):
    """The index of the first node called `name`; ValueError naming `what` when none."""
    for i, node in enumerate(scene.nodes):
        if node.name == name:
            return i
    raise ValueError(f"{what}: no node named {name!r}")


def _render(scene, entry):
    """Scene.render from the sidecar's `render`."""
    return Render(
        size=np.array(entry["size"], np.int64),
        camera=_node_index(scene, entry["camera"], "sidecar render camera"),
        exposure=float(entry.get("exposure", 0.0)),
        view_transform=entry.get("view_transform", ""),
        look=entry.get("look", ""),
        gamma=float(entry.get("gamma", 1.0)),
    )


def _world(entry):
    """Scene.world from the sidecar's `world`."""
    return World(
        color=np.array(entry.get("color", [0.0, 0.0, 0.0]), np.float64),
        strength=float(entry.get("strength", 1.0)),
        environment=entry.get("environment"),
        rotation=np.array(entry.get("rotation", [0.0, 0.0, 0.0]), np.float64),
    )


def _area_light(scene, entry):
    """An area Light on a new root node with the entry's matrix."""
    scene.lights.append(
        Light(
            kind="area",
            color=np.array(entry["color"], np.float64),
            intensity=float(entry["power"]),
            shape=entry["shape"],
            size=np.array(entry["size"], np.float64),
        )
    )
    matrix = np.array(entry["matrix"], np.float64).reshape(4, 4)
    scene.nodes.append(
        Node(
            name=entry["name"],
            local=matrix,
            world=matrix.copy(),
            light=len(scene.lights) - 1,
        )
    )


def _instance_table(scene, path):
    """Each named node's instances from the table's `node_names`, `starts`, `matrices`."""
    with np.load(path, allow_pickle=False) as table:
        names, starts = table["node_names"], table["starts"]
        matrices = table["matrices"].astype(np.float32, copy=False)
    if len(starts) != len(names) + 1:
        raise ValueError(f"instance table: {len(starts)} starts for {len(names)} names")
    for i, name in enumerate(names):
        node = scene.nodes[_node_index(scene, str(name), "instance table")]
        node.instances = matrices[starts[i] : starts[i + 1]]
    return int(starts[-1]) if len(starts) else 0


def apply(scene, path):
    """Applies the sidecar at `path` to `scene` and adds the notes of what it did."""
    path = Path(path)
    doc = json.loads(path.read_text())
    if doc.get("version") != VERSION:
        raise ValueError(f"sidecar version {doc.get('version')!r}: not supported")
    scene.notes.append(Note("used", "sidecar", 1, str(doc.get("source", {}))))
    if doc.get("world") is not None:
        scene.world = _world(doc["world"])
    if doc.get("render") is not None:
        scene.render = _render(scene, doc["render"])
    areas = doc.get("area_lights", [])
    for entry in areas:
        _area_light(scene, entry)
    if areas:
        scene.notes.append(Note("used", "area lights", len(areas)))
    table = doc.get("instances")
    if table is not None:
        names = _instance_table(scene, path.parent / table["file"])
        scene.notes.append(Note("used", "instance table", names, table["file"]))
    for key, what in NOT_EXPORTED:
        for name in doc.get("not_exported", {}).get(key, []):
            scene.notes.append(Note("dropped", f"{what} not exported", 1, name))
