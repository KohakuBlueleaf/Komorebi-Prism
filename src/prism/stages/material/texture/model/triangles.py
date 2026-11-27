"""Per triangle: texel areas, the material word, whether it has a tangent frame, and the
shade blocks beside the raster stage's mesh blocks."""

import numpy as np

from prism.stages.material.texture.model.numbers import F32, LEVEL_SLOTS, SH
from prism.stages.raster.model.numbers import LANES
from prism.stages.raster.model.records import mesh_blocks as raster_blocks
from prism_reference.material.kinds import FLAT, TRANSPARENT
from prism_reference.material.texture import map_area, uv_maps
from prism_reference.raster.vector import cross3, dot3, normalized


def texel_areas(materials):
    """Per triangle the doubled uv area in level 0 texels of its albedo, normal and
    specular textures ((3, T) float32; each times its slot's uv map's area) and its
    material word, material | each one's levels << 16, 20, 24 (levels 1 without that
    texture)."""
    uv = materials["uv"]
    du1, dv1 = uv[:, 1, 0] - uv[:, 0, 0], uv[:, 1, 1] - uv[:, 0, 1]
    du2, dv2 = uv[:, 2, 0] - uv[:, 0, 0], uv[:, 2, 1] - uv[:, 0, 1]
    uv_area2 = np.abs(du1 * dv2 - du2 * dv1)
    word = materials["material"].astype(np.uint32)
    areas = np.zeros((len(LEVEL_SLOTS), len(uv)), dtype=F32)
    maps = uv_maps(materials)[materials["material"]]
    for index, slot in enumerate(LEVEL_SLOTS):
        own = materials["textures"][materials["material"], slot]
        texture = np.maximum(own, 0)
        size = materials["mip"][texture, 0]
        texels = uv_area2 * (size[:, 1] * size[:, 2]).astype(F32)
        texels = texels * map_area(maps[:, slot])
        areas[index] = np.where(np.isfinite(texels), texels, F32(0))
        levels = np.where(own >= 0, materials["levels"][texture], 1).astype(np.uint32)
        word |= levels << (16 + 4 * index)
    return areas, word


def frame_ok(scene, materials):
    """Per triangle the reference's `frame_ok` (shade_setup's float32 steps, the camera
    left out): its coordinates give a tangent frame."""
    p = scene["positions"][scene["indices"]]
    uv = materials["uv"]
    e1, e2 = p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]
    normal = normalized(cross3(e1, e2))
    du1, dv1 = uv[:, 1, 0] - uv[:, 0, 0], uv[:, 1, 1] - uv[:, 0, 1]
    du2, dv2 = uv[:, 2, 0] - uv[:, 0, 0], uv[:, 2, 1] - uv[:, 0, 1]
    det = du1 * dv2 - du2 * dv1
    sign = np.where(det < 0, F32(-1), F32(1))[:, None]
    tangent = (e1 * dv2[:, None] - e2 * dv1[:, None]) * sign
    tangent = normalized(tangent - normal * dot3(normal, tangent)[:, None])
    return (det != 0) & (dot3(tangent, tangent) > 0)


def mesh_blocks(scene, materials, lit=False):
    """The raster stage's mesh blocks with corner colours replaced by u, v and light term
    where not flat (lit: all), and the shade blocks (blocks, 128): 32 albedo texel areas,
    32 material words (lit: kShadeNoFrame where not frame_ok or transparent), 32 normal,
    32 specular."""
    kind = materials["kind"][materials["material"]]
    values = np.concatenate(
        [materials["uv"], materials["light"][:, :, None]], axis=2
    ).astype(F32)
    shaded = np.ones(len(kind), dtype=bool) if lit else kind != FLAT
    colors = np.where(shaded[:, None, None], values, scene["colors"][scene["indices"]])
    flat_scene = {
        **scene,
        "positions": scene["positions"][scene["indices"]].reshape(-1, 3),
        "colors": colors.reshape(-1, 3).astype(F32),
        "indices": np.arange(3 * len(scene["indices"])).reshape(-1, 3),
    }
    blocks = raster_blocks(flat_scene)
    areas, word = texel_areas(materials)
    if lit:
        framed = frame_ok(scene, materials) & (kind != TRANSPARENT)
        word = np.where(framed, word, word | np.uint32(SH["kShadeNoFrame"]))
    count = len(blocks) * LANES
    shade = np.zeros((4, count), dtype=np.uint32)
    shade[0, : len(word)] = areas[0].view(np.uint32)
    shade[1, : len(word)] = word
    shade[2:, : len(word)] = areas[1:].view(np.uint32)
    shade_blocks = shade.reshape(4, len(blocks), LANES).transpose(1, 0, 2)
    return blocks, np.ascontiguousarray(shade_blocks.reshape(len(blocks), -1))
