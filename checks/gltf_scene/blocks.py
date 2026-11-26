"""The layers' blocks made once: `layer_blocks` twice on one scene (the second loads what
the first kept) against a fresh computation, unlit and lit; a changed uv another key."""

import os

import numpy as np

from checks.gltf_scene.cases import same
from prism.stages.material.texture.model import blocks
from prism.stages.material.texture.model.blocks import as_shaded, layer, layer_blocks
from prism.stages.material.texture.model.triangles import mesh_blocks
from prism_common.paths import CACHE_VARIABLE
from prism_reference.material.kinds import MASKED, TRANSPARENT
from prism_reference.scene.public.materials import load_materials
from prism_reference.scene.public.mesh import load_mesh


def fresh(scene, materials, lights):
    """[(name, indices, mesh blocks, shade blocks, triangles)] as `layers.prepare`
    computed them before they were kept."""
    lit = lights is not None
    if lit:
        materials = {**materials, "light": lights["visibility"][scene["indices"]]}
    else:
        materials = as_shaded(materials)
    kind = materials["kind"][materials["material"]]
    keeps = {
        "opaque": (kind != MASKED) & (kind != TRANSPARENT),
        "masked": kind == MASKED,
        "glass": kind == TRANSPARENT,
    }
    out = []
    for name, keep in keeps.items():
        if name != "opaque" and not keep.any():
            continue
        layer_scene, layer_materials = layer(scene, materials, keep)
        made, shade = mesh_blocks(layer_scene, layer_materials, lit)
        out.append((name, layer_scene["indices"], made, shade, int(keep.sum())))
    return out


def byte_equal(a, b):
    """Whether two arrays have one dtype, one shape and the same bytes."""
    a, b = np.ascontiguousarray(a), np.ascontiguousarray(b)
    return a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes()


def kept_case(label, scene, materials, lights):
    """Made, then loaded (the process's dict emptied): each layer's arrays equal byte
    for byte to the fresh computation, the second's read from the kept files."""
    blocks.MADE.clear()
    first = layer_blocks(scene, materials, lights)
    blocks.MADE.clear()
    second = layer_blocks(scene, materials, lights)
    want = fresh(scene, materials, lights)
    same(f"{label}: layers", [one[0] for one in second], [one[0] for one in want])
    for got, made, expect in zip(second, first, want):
        name, layer_scene, mesh, shade, triangles = got
        arrays = (layer_scene["indices"], mesh, shade)
        equal = all(byte_equal(a, b) for a, b in zip(arrays, expect[1:4]))
        same(f"{label}: {name} equal to a fresh computation", equal, True)
        same(f"{label}: {name} triangles", triangles, expect[4])
        same(f"{label}: {name} loaded", isinstance(mesh, np.memmap), True)
        same(f"{label}: {name} first made", isinstance(made[2], np.memmap), False)


def blocks_cases(name, data, folder):
    """The kept cases unlit and lit (a seeded visibility a vertex), then a changed uv
    value: another key and folder, under a cache root in `folder`."""
    previous = os.environ.get(CACHE_VARIABLE)
    os.environ[CACHE_VARIABLE] = str(folder / "cache")
    try:
        scene, _ = load_mesh(name, data)
        materials, _ = load_materials(name, data)
        rng = np.random.default_rng(3)
        visibility = rng.random(len(scene["positions"]), dtype=np.float32)
        lights = {"visibility": visibility}
        same(
            "blocks: the scene has masked and glass layers",
            len(fresh(scene, materials, None)),
            3,
        )
        kept_case("blocks unlit", scene, materials, None)
        kept_case("blocks lit", scene, materials, lights)
        uv = materials["uv"].copy()
        uv[0, 0, 0] += np.float32(0.25)
        changed = {**materials, "uv": uv}
        key = blocks.digest(scene, as_shaded(materials), False)
        other = blocks.digest(scene, as_shaded(changed), False)
        same("blocks: a changed uv, another key", key != other, True)
        layer_blocks(scene, changed, None)
        kept = sorted(p.name for p in (folder / "cache" / "blocks").iterdir())
        names = {key[: blocks.NAME_DIGITS], other[: blocks.NAME_DIGITS]}
        same("blocks: a changed uv, another folder", names <= set(kept), True)
    finally:
        if previous is None:
            os.environ.pop(CACHE_VARIABLE, None)
        else:
            os.environ[CACHE_VARIABLE] = previous
        blocks.MADE.clear()
