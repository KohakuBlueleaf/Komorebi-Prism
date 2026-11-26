"""The frame's layers as the card holds them, for the model: each layer's triangles read
back from the mesh blocks a host writes, its shade rows, and each piece's 32-word list
record as place writes it (a shaded layer: colour planes times 1/z, the shade word)."""

import numpy as np

from prism.stages.material.texture.model.blocks import layer_blocks
from prism.stages.raster.model.numbers import BLOCK_SLOTS, LANES, K, S
from prism.stages.raster.model.records import (
    bits,
    mesh_blocks,
    pack_records,
    window_words,
)
from prism_reference.raster.setup import setup

CORNER_WORDS = 9  # a corner block's x, y, z of three corners, then their colours
TEXTURES = 3  # the albedo, normal and specular levels of a shade word
INT32 = np.int64  # the shade word's arithmetic, wide enough for its int32 steps


def flat_scene(blocks, triangles, scene):
    """The scene of `triangles` triangles read back from mesh blocks (blocks, 576):
    a corner each, its colour as the blocks hold it; the view's other keys kept."""
    vectors = blocks[:, window_words(BLOCK_SLOTS)].view(np.float32)
    vectors = vectors.reshape(len(blocks), BLOCK_SLOTS, LANES).transpose(0, 2, 1)
    vectors = vectors.reshape(-1, BLOCK_SLOTS)[:triangles]
    positions = vectors[:, :CORNER_WORDS].reshape(-1, 3)
    colours = vectors[:, CORNER_WORDS : 2 * CORNER_WORDS].reshape(-1, 3)
    return {
        **scene,
        "positions": np.ascontiguousarray(positions),
        "colors": np.ascontiguousarray(colours),
        "indices": np.arange(3 * triangles).reshape(-1, 3),
    }


def shade_rows(shade_blocks):
    """(4, triangles) uint32 of shade blocks (blocks, 128): albedo texels, material
    word, normal texels, specular texels a triangle."""
    count = len(shade_blocks)
    rows = shade_blocks.reshape(count, 4, LANES).transpose(1, 0, 2)
    return np.ascontiguousarray(rows.reshape(4, count * LANES))


def frame_layers(scene, materials=None, lights=None, order=None):
    """[(name, flat scene, shade rows or None)] of the frame's layers: without
    materials the scene's one, unshaded; with, the material model's layers, shaded;
    `order` the frame's layer names (None: the model's order)."""
    if materials is None:
        blocks = mesh_blocks(scene)
        return [("opaque", flat_scene(blocks, len(scene["indices"]), scene), None)]
    made = {
        name: (flat_scene(blocks, triangles, scene), shade_rows(shade))
        for name, _, blocks, shade, triangles in layer_blocks(scene, materials, lights)
    }
    order = list(made) if order is None else list(order)
    missing = [name for name in order if name not in made]
    if missing:
        raise ValueError(f"layers {missing}: the scene has {list(made)}")
    return [(name, *made[name]) for name in order]


def shade_word(area_bits, shade):
    """The shade word of each piece (setup's shade_word): `area_bits` (n,) its doubled
    area's float32 bits, `shade` (4, n) its triangle's shade rows."""
    material = shade[1].astype(INT32)
    word = material & (0xFFFF | S["kShadeWordKept"])
    area = area_bits.astype(np.uint32).view(np.int32).astype(INT32)
    finite = np.where(area < 0, 0, (255 - (area >> 23)) >> 1)
    for texture in range(TEXTURES):
        top = ((material >> (16 + 4 * texture)) & 0xF) - 1
        texels = shade[0 if texture == 0 else 1 + texture].astype(np.uint32)
        texels = texels.view(np.int32).astype(INT32)
        stepped = (((texels - area - 1) >> 23) + 1) >> 1
        stepped = np.minimum(np.minimum(stepped, finite), top)
        level = np.where(
            texels > 0x7F800000,
            top,
            np.where((area >= 0) & (texels > area), stepped, 0),
        )
        level = np.where(top > 0, level, 0)
        word |= level << (16 + 4 * texture)
    return word.astype(np.uint32)


def card_records(scene, shade=None):
    """(the pieces of setup(scene), their 32-word records as place writes them): a
    shaded layer's colour planes weighted by 1/z, its shade word from `shade`."""
    if shade is None:
        pieces = setup(scene)
        return pieces, pack_records(pieces)
    corner_values = scene["colors"][scene["indices"]].astype(np.float32)
    pieces = setup(scene, extra=corner_values)
    packed = pack_records(pieces)
    weighted = pieces["extra_planes"]  # (n, coefficient, channel)
    for channel in range(3):
        column = K["kRecCol"] + 3 * channel
        packed[:, column : column + 3] = bits(weighted[:, :, channel])
    tri = pieces["tri"].astype(np.int64)
    packed[:, S["kRecShadeWord"]] = shade_word(bits(pieces["area2"]), shade[:, tri])
    return pieces, packed
