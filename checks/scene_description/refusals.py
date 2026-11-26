"""Each refusal of the importer, the sidecar, `check` and `flatten` raised on a file made
for it."""

import copy

import numpy as np

from checks.scene_description import build, roundtrip
from checks.scene_description.compare import refused
from prism_reference.scene.description.check import check
from prism_reference.scene.description.flatten import flatten
from prism_reference.scene.importers.gltf import load


def _variant(folder, name, change):
    """Writes the quad scene as `<name>.glb` after `change(doc)`; returns its path."""
    doc, w, _ = build.document()
    doc = copy.deepcopy(doc)
    change(doc, w)
    path = folder / f"{name}.glb"
    build.write_glb(path, doc, w)
    return path


def _required(name):
    """A change adding `name` to extensionsRequired."""
    return lambda doc, w: doc["extensionsRequired"].append(name)


def run(folder):
    """Raises every refusal and records each."""
    for name in (
        "KHR_draco_mesh_compression",
        "EXT_meshopt_compression",
        "KHR_texture_basisu",
    ):
        path = _variant(folder, name.lower(), _required(name))
        refused(f"required {name}", lambda p=path: load(p), name)
    path = _variant(folder, "version", lambda doc, w: None)
    sidecar = dict(roundtrip.SIDECAR, version=2)
    roundtrip.write_sidecar(path, sidecar)
    refused("sidecar version", lambda: load(path), "sidecar version 2")
    path = _variant(folder, "camera", lambda doc, w: None)
    render = dict(roundtrip.SIDECAR["render"], camera="no such camera")
    roundtrip.write_sidecar(path, dict(roundtrip.SIDECAR, render=render))
    refused("render camera name", lambda: load(path), "no such camera")
    path = _variant(folder, "table", lambda doc, w: None)
    roundtrip.write_sidecar(path, names=("no such node",))
    refused("instance table name", lambda: load(path), "no such node")
    plain = _variant(folder, "plain", lambda doc, w: None)
    scene = load(plain)
    refused("flatten over its limit", lambda: flatten(scene, 14), "15 triangles")
    scene.nodes[0].parent = 2
    refused("check parent cycle", lambda: check(scene), "parent cycle")
    scene = load(plain)
    scene.nodes[1].mesh = 7
    refused("check mesh index", lambda: check(scene), "index 7")
    scene = load(plain)
    tri = scene.meshes[1].primitives[0]
    tri.indices = np.array([[0, 1, 3]], np.uint32)
    refused(
        "check indices past vertices", lambda: check(scene), "at or past 3 vertices"
    )
    tri.indices = np.array([[0, 1, 2]], np.uint32)
    tri.normals = np.zeros((2, 3), np.float32)
    refused("check attribute length", lambda: check(scene), "2 entries for 3 vertices")
    tri.normals = None
    tri.positions = np.full((3, 3), np.nan, np.float32)
    refused("check non-finite positions", lambda: check(scene), "not finite")
