"""Each layer of a shaded frame (opaque, masked, glass): its scene, mesh and shade blocks,
made once for a scene and its materials and kept under the cache root."""

import concurrent.futures
import itertools
import json
import os

import numpy as np

from prism.stages.material.texture.model.triangles import mesh_blocks
from prism.stages.raster.model.numbers import LANES
from prism_common.digest import Digest
from prism_common.paths import cache_root
from prism_reference.material.kinds import LIT, MASKED, TEXTURED, TRANSPARENT
from prism_reference.material.texture import uv_maps

VERSION = 2  # of what is kept: another value keys every scene anew
SCENE_KEYS = ("positions", "indices", "colors")
MATERIAL_KEYS = ("uv", "light", "material", "kind", "textures", "mip", "levels")
ARRAYS = ("indices", "blocks", "shade_blocks")  # a layer's files
PER_TRIANGLE = ("uv", "light", "material")  # the materials' arrays a triangle each
NAME_DIGITS = 16  # of the digest, naming the folder
MADE = {}  # by digest: what this process has made or loaded


def layer(scene, materials, keep):
    """The scene and the materials of the triangles `keep` (a bool per triangle, or a
    slice), in their order: a layer's mesh."""
    per_triangle = {name: materials[name][keep] for name in PER_TRIANGLE}
    return {**scene, "indices": scene["indices"][keep]}, {**materials, **per_triangle}


def blocks_of(scene, materials, lit):
    """`mesh_blocks` of runs of whole blocks on the process's CPUs, joined in order."""
    count = len(scene["indices"])
    runs = -(-count // LANES)
    cuts = LANES * np.linspace(0, runs, len(os.sched_getaffinity(0)) + 1).astype(int)
    spans = [(a, min(b, count)) for a, b in itertools.pairwise(cuts) if a < b]
    if len(spans) < 2:
        return mesh_blocks(scene, materials, lit)

    def run(span):
        return mesh_blocks(*layer(scene, materials, slice(*span)), lit)

    with concurrent.futures.ThreadPoolExecutor(len(spans)) as pool:
        made = list(pool.map(run, spans))
    return tuple(np.concatenate(part) for part in zip(*made))


def as_shaded(materials):
    """A copy of the materials with the lit kind made textured: what SHADE shades
    unlit."""
    kind = materials["kind"].copy()
    kind[kind == LIT] = TEXTURED
    return {**materials, "kind": kind}


def entering(materials, lights, indices):
    """The materials as the blocks take them: unlit as shaded; lit with the corners'
    light term the lights' visibility."""
    if lights is None:
        return as_shaded(materials)
    return {**materials, "light": lights["visibility"][indices]}


def digest(scene, materials, lit):
    """The hex digest (`Digest`) of the version, the lit flag and every array entering
    the blocks (its dtype, shape and bytes), the slots' uv maps among them."""
    hasher = Digest()
    hasher.update(f"{VERSION} {int(lit)}".encode())
    arrays = [scene[k] for k in SCENE_KEYS] + [materials[k] for k in MATERIAL_KEYS]
    arrays.append(uv_maps(materials))
    for array in arrays:
        array = np.ascontiguousarray(array)
        hasher.update(f"{array.dtype.str} {array.shape}".encode())
        hasher.update(memoryview(array.reshape(-1)).cast("B"))
    return hasher.hexdigest()


def computed(scene, materials, lit):
    """{name: (indices or None for the scene's own, blocks, shade blocks)} of the
    layers the scene has, opaque always and first."""
    kind = materials["kind"][materials["material"]]
    keeps = {
        "opaque": (kind != MASKED) & (kind != TRANSPARENT),
        "masked": kind == MASKED,
        "glass": kind == TRANSPARENT,
    }
    made = {}
    for name, keep in keeps.items():
        if name != "opaque" and not keep.any():
            continue
        if keep.all():
            layer_scene, layer_materials = scene, materials
        else:
            layer_scene, layer_materials = layer(scene, materials, keep)
        blocks, shade_blocks = blocks_of(layer_scene, layer_materials, lit)
        own = None if keep.all() else layer_scene["indices"]
        made[name] = (own, blocks, shade_blocks)
    return made


def saved(array, path):
    """`array` written to `path` whole: a temporary name, then renamed."""
    part = path.with_name(f"{path.name}.{os.getpid()}.part")
    with open(part, "wb") as out:
        np.save(out, np.ascontiguousarray(array))
    part.replace(path)


def written(folder, key, made):
    """Every layer's arrays into `folder`, then the key file naming the digest and the
    layers."""
    folder.mkdir(parents=True, exist_ok=True)
    layers = {}
    for name, arrays in made.items():
        layers[name] = [array is not None for array in arrays]
        for part, array in zip(ARRAYS, arrays):
            if array is not None:
                saved(array, folder / f"{name}_{part}.npy")
    text = json.dumps({"digest": key, "version": VERSION, "layers": layers})
    part = folder / f"key.json.{os.getpid()}.part"
    part.write_text(text)
    part.replace(folder / "key.json")


def loaded(folder, key):
    """The layers kept in `folder` for the digest `key` (arrays read with mmap); None
    when absent or another digest's."""
    path = folder / "key.json"
    if not path.is_file():
        return None
    entry = json.loads(path.read_text())
    if entry.get("digest") != key:
        return None
    made = {}
    for name, present in entry["layers"].items():
        made[name] = tuple(
            np.load(folder / f"{name}_{part}.npy", mmap_mode="r") if there else None
            for part, there in zip(ARRAYS, present)
        )
    return made


def layer_blocks(scene, materials, lights=None):
    """[(name, scene, mesh blocks, shade blocks, triangles)] of the opaque, masked and
    glass layers the scene has (opaque always, first): unlit the materials as shaded,
    lit (with `lights`) every corner's light term its baked visibility."""
    lit = lights is not None
    shaded = entering(materials, lights, scene["indices"])
    key = digest(scene, shaded, lit)
    if key not in MADE:
        folder = cache_root() / "blocks" / key[:NAME_DIGITS]
        made = loaded(folder, key)
        if made is None:
            made = computed(scene, shaded, lit)
            written(folder, key, made)
        MADE[key] = made
    layers = []
    for name, (own, blocks, shade_blocks) in MADE[key].items():
        layer_scene = scene if own is None else {**scene, "indices": own}
        triangles = len(layer_scene["indices"])
        layers.append((name, layer_scene, blocks, shade_blocks, triangles))
    return layers
