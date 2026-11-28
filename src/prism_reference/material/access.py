"""The texture pages SHADE reads over a frame, as lit SHADE keys them: per pixel of a
layer its albedo's, normal's, specular's and (merging) mask's page, numbered with every
level of every texture in 32 x 32 pages, one after another."""

import numpy as np

from prism_reference.material.kinds import (
    ALBEDO,
    LIT,
    MASK,
    MASKED,
    NORMAL,
    SPECULAR,
    TRANSPARENT,
)
from prism_reference.material.texture import mapped_uv, texel_xy, uv_maps
from prism_reference.raster.frames import pixel_values

PAGE = 32  # a texture page: 32 x 32 texels of one level, 4 KB
KEYS = 4  # albedo, normal, specular, mask
NONE = -1  # no page


def texture_firsts(materials):
    """Per (texture, level) its first page and its pages across ((N, levels, 2) int64):
    every level of every texture in pages of PAGE x PAGE texels, row by row."""
    mip, levels = materials["mip"], materials["levels"]
    out = np.zeros((len(levels), mip.shape[1], 2), dtype=np.int64)
    first = 0
    for texture in range(len(levels)):
        for level in range(levels[texture]):
            width, height = int(mip[texture, level, 1]), int(mip[texture, level, 2])
            across, down = -(-width // PAGE), -(-height // PAGE)
            out[texture, level] = first, across
            first += across * down
    return out


def shade_pixels(layers):
    """Per layer the pixels (H, W) lit SHADE keys: the opaque and glass layers' covered
    ones, the masked layer's where its 1/z bits are above the opaque layer's."""
    opaque, masked = layers["opaque"], layers["masked"]
    nearer = masked["depth"].view(np.uint32) > opaque["depth"].view(np.uint32)
    return {
        "opaque": opaque["tri"] >= 0,
        "masked": (masked["tri"] >= 0) & nearer,
        "glass": layers["glass"]["tri"] >= 0,
    }


def layer_pages(materials, prepared, layer, where, firsts, merging):
    """Pages (H, W, 4) a layer's pixels `where` read and their texels (H, W, 4, 3: group,
    column, row) at each slot's mapped uv: albedo, normal (framed, not glass), specular
    (with the term), mask (`merging`, masked); NONE else."""
    out = np.full(where.shape + (KEYS,), NONE, dtype=np.int64)
    texels = np.full(where.shape + (KEYS, 3), NONE, dtype=np.int32)
    ys, xs = np.nonzero(where)
    t = layer["tri"][ys, xs]
    m = materials["material"][t]
    kind = materials["kind"][m]
    _, _, _, u, v, _ = pixel_values(layer, prepared, ys, xs)
    texture = materials["textures"][m]
    maps = uv_maps(materials)[m]
    framed = prepared["frame_ok"][t] & (kind != TRANSPARENT)
    shiny = ((kind == LIT) | (kind == TRANSPARENT)) & (
        materials["specular"][m].max(axis=1) > 0
    )
    keyed = (
        (ALBEDO, ALBEDO, texture[:, ALBEDO] >= 0),
        (NORMAL, NORMAL, framed & (texture[:, NORMAL] >= 0)),
        (SPECULAR, SPECULAR, shiny & (texture[:, SPECULAR] >= 0)),
        (MASK, ALBEDO, merging & (kind == MASKED) & (texture[:, MASK] >= 0)),
    )
    for column, (slot, level_slot, take) in enumerate(keyed):
        take = take & (texture[:, ALBEDO] >= 0 if slot == MASK else True)
        if not take.any():
            continue
        tex = texture[take, slot]
        level = prepared["level"][t[take], level_slot]
        su, sv = mapped_uv(maps[take, slot], u[take], v[take])
        x, y, _ = texel_xy(materials, tex, level, su, sv)
        first, across = firsts[tex, level, 0], firsts[tex, level, 1]
        out[ys[take], xs[take], column] = first + (y // PAGE) * across + x // PAGE
        group = tex * firsts.shape[1] + level
        texels[ys[take], xs[take], column] = np.stack([group, x, y], 1)
    return out, texels


def page_groups(materials, firsts):
    """Per page its (texture, level) group, column and row in that level's pages: three
    (pages,) int64 arrays, the group texture x levels + level."""
    levels_max = firsts.shape[1]
    group, column, row = [], [], []
    for texture in range(len(materials["levels"])):
        for level in range(materials["levels"][texture]):
            width, height = materials["mip"][texture, level, 1:]
            across, down = -(-int(width) // PAGE), -(-int(height) // PAGE)
            group.append(np.full(across * down, texture * levels_max + level))
            column.append(np.tile(np.arange(across), down))
            row.append(np.repeat(np.arange(down), across))
    if not group:
        return (np.zeros(0, dtype=np.int64),) * 3
    return tuple(np.concatenate(a).astype(np.int64) for a in (group, column, row))
