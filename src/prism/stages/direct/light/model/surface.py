"""The surface planes as images and as the reference gives them, the lit frame's
reference, and the sun's shadow edge band."""

import numpy as np

from prism.stages.direct.light.model.numbers import F32, SURFACE
from prism.stages.material.texture.model.layers import later_pieces
from prism.stages.material.texture.model.table import exponents
from prism.stages.raster.model.frame import TILE_ORDER
from prism.stages.raster.model.numbers import K
from prism_reference.direct.frame import TERMS, rasterize_lighted
from prism_reference.direct.shadow import sun_shadow
from prism_reference.material.kinds import EMISSIVE
from prism_reference.raster.fill import TILES_X, TILES_Y
from prism_reference.raster.setup import world_points


def decode_planes(pages, grid=(TILES_X, TILES_Y)):
    """Frame pages (tiles x 5, 1024) as five images (5, H, W) of uint32: the padded
    frame of `grid` (TX, TY), tile ty TX + tx."""
    across, down = grid
    planes = np.asarray(pages, dtype=np.uint32).reshape(-1, K["kPlanes"], 1024)
    pixels = planes[: across * down, :, TILE_ORDER].reshape(
        down, across, K["kPlanes"], 32, 32
    )
    return pixels.transpose(2, 0, 3, 1, 4).reshape(K["kPlanes"], 32 * down, 32 * across)


def reference_surface(view, materials, lights):
    """The reference's merged surface of a camera from rasterize_lighted's parts (terms:
    the specular and the glass only): a (emissive x emissive_scale), normal, visibility,
    specular, material word, 1/z, triangle, later pieces, and the parts."""
    lit = rasterize_lighted(view, materials, lights, terms=("specular", "glass"))
    parts, tri = lit["parts"], lit["tri"]
    material = np.maximum(parts["material"], 0)
    kind = materials["kind"][material]
    emissive = (parts["material"] >= 0) & (kind == EMISSIVE)
    scale = np.where(emissive, F32(lights["emissive_scale"]), F32(1))
    word = (
        material.astype(np.uint32)
        | kind.astype(np.uint32) << SURFACE["kMaterialKindShift"]
        | exponents(materials)[material] << SURFACE["kMaterialExponentShift"]
    )
    corner = {**materials, "light": lights["visibility"][view["indices"]]}
    return {
        "a": parts["albedo"] * scale[..., None],
        "normal": parts["normal"],
        "visibility": parts["visibility"],
        "specular": parts["specular"],
        "material": np.where(parts["material"] >= 0, word, np.uint32(0xFFFFFFFF)),
        "depth": lit["depth"],
        "tri": tri,
        "later": later_pieces(view, corner, tri),
        "parts": parts,
    }


def light_reference(view, materials, lights, terms=TERMS):
    """The lit frame's reference: rasterize_lighted with `terms` (all: the default
    frame), the 2 x 2 filter."""
    return rasterize_lighted(view, materials, lights, terms=terms)


def shadow_band(view, lights, lit):
    """The pixels of the sun's shadow edge band: the reference's sun_shadow (2 x 2
    filter) strictly between 0 and 1 at the pixel's point and normal (lit's parts),
    and their neighbours (one pixel)."""
    tri = lit["tri"]
    ys, xs = np.nonzero(tri >= 0)
    px = xs.astype(F32) + F32(0.5)
    py = ys.astype(F32) + F32(0.5)
    points = world_points(view["camera"], px, py, lit["depth"][ys, xs])
    share = sun_shadow(lights, points, lit["parts"]["normal"][ys, xs])
    edge = np.zeros(tri.shape, dtype=bool)
    edge[ys, xs] = (share > 0) & (share < 1)
    band = edge.copy()
    band[1:] |= edge[:-1]
    band[:-1] |= edge[1:]
    band[:, 1:] |= band[:, :-1].copy()
    band[:, :-1] |= band[:, 1:].copy()
    return band & (tri >= 0)
