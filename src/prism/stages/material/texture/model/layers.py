"""The layers of a shaded frame (opaque, masked, glass) and what is uploaded once for it:
mesh and shade blocks, texture pages, SHADE's table."""

import numpy as np

from prism.stages.material.texture.model.numbers import F32, KEY_PAGES
from prism.stages.material.texture.model.table import table
from prism.stages.material.texture.model.textures import texture_pages
from prism.stages.material.texture.model.triangles import mesh_blocks
from prism_reference.material.kinds import LIT, MASKED, TEXTURED, TRANSPARENT
from prism_reference.raster.setup import setup


def layer(scene, materials, keep):
    """The scene and the materials of the triangles `keep` (a bool per triangle), in
    their order: a layer's mesh."""
    per_triangle = {name: materials[name][keep] for name in ("uv", "light", "material")}
    return {**scene, "indices": scene["indices"][keep]}, {**materials, **per_triangle}


def prepare(scene, materials, lights=None):
    """Everything uploaded once for a shaded frame (`lights`: corner light terms the
    baked visibility): mesh and shade blocks, pages, table; masked triangles a mesh of
    their own ("masked_*"), transparent too ("glass_*"), the others without."""
    lit = lights is not None
    if lit:
        materials = {**materials, "light": lights["visibility"][scene["indices"]]}
    kind = materials["kind"][materials["material"]]
    prepared = {}
    others = np.ones(len(kind), dtype=bool)
    for name, value in (("masked", MASKED), ("glass", TRANSPARENT)):
        keep = kind == value
        if not keep.any():
            continue
        layer_scene, layer_materials = layer(scene, materials, keep)
        blocks, shade_blocks = mesh_blocks(layer_scene, layer_materials, lit)
        prepared[f"{name}_blocks"] = blocks
        prepared[f"{name}_shade_blocks"] = shade_blocks
        prepared[f"{name}_triangles"] = int(keep.sum())
        others &= ~keep
    if others.all():
        materials_kept = materials
    else:
        scene, materials_kept = layer(scene, materials, others)
    blocks, shade_blocks = mesh_blocks(scene, materials_kept, lit)
    pages, entries = texture_pages(materials)
    if len(pages) > KEY_PAGES:
        raise ValueError(
            f"the textures take {len(pages)} pages; a texel's key holds {KEY_PAGES}"
        )
    scale = lights["emissive_scale"] if lit else 1.0
    return {
        **prepared,
        "blocks": blocks,
        "shade_blocks": shade_blocks,
        "pages": pages,
        "table": table(materials, entries, len(pages), scale),
    }


def as_shaded(materials):
    """A copy of the materials with the lit kind made textured: what SHADE shades
    unlit."""
    kind = materials["kind"].copy()
    kind[kind == LIT] = TEXTURED
    return {**materials, "kind": kind}


def later_pieces(view, materials, tri):
    """Pixels whose triangle `tri` (H, W) the near plane cut and which lie on a piece
    after its first kept one."""
    extra = np.concatenate([materials["uv"], materials["light"][:, :, None]], axis=2)
    records = setup(view, extra)
    owner = records["tri"]
    later = np.flatnonzero(np.r_[False, owner[1:] == owner[:-1]])
    mask = np.zeros(tri.shape, dtype=bool)
    for piece in later:
        x0, x1, y0, y1 = records["box"][piece]
        ys, xs = np.nonzero(tri[y0 : y1 + 1, x0 : x1 + 1] == owner[piece])
        px, py = (xs + x0).astype(F32) + F32(0.5), (ys + y0).astype(F32) + F32(0.5)
        edges = (
            records["a"][piece] * px[:, None] + records["b"][piece] * py[:, None]
        ) + records["c"][piece]
        inside = (edges >= 0).all(axis=1) | (edges <= 0).all(axis=1)
        mask[ys[inside] + y0, xs[inside] + x0] = True
    return mask
