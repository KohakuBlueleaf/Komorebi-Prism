"""The layers of a shaded frame (opaque, masked, glass) and what is uploaded once for it:
mesh and shade blocks, texture pages, SHADE's table."""

import numpy as np

from prism.stages.material.texture.model.blocks import as_shaded, layer_blocks
from prism.stages.material.texture.model.numbers import F32, KEY_PAGES
from prism.stages.material.texture.model.table import table
from prism.stages.material.texture.model.textures import texture_pages
from prism_reference.raster.setup import setup

__all__ = ["as_shaded", "later_pieces", "prepare"]


def prepare(scene, materials, lights=None, size=None):
    """Everything uploaded once for a shaded frame (`lights`: corner light terms the
    baked visibility): mesh and shade blocks, pages, table (of `size` words); masked
    triangles a mesh of their own ("masked_*"), transparent too ("glass_*")."""
    lit = lights is not None
    if lit:
        materials = {**materials, "light": lights["visibility"][scene["indices"]]}
    prepared = {}
    for name, _, blocks, shade_blocks, triangles in layer_blocks(
        scene, materials, lights
    ):
        prefix = "" if name == "opaque" else f"{name}_"
        prepared[f"{prefix}blocks"] = blocks
        prepared[f"{prefix}shade_blocks"] = shade_blocks
        if name != "opaque":
            prepared[f"{name}_triangles"] = triangles
    pages, entries = texture_pages(materials)
    if len(pages) > KEY_PAGES:
        raise ValueError(
            f"the textures take {len(pages)} pages; a texel's key holds {KEY_PAGES}"
        )
    scale = lights["emissive_scale"] if lit else 1.0
    return {
        **prepared,
        "pages": pages,
        "table": table(materials, entries, len(pages), scale, size),
    }


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
