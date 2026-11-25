"""The field as LIGHT reads it: its dense pages (a block of voxels a page), the
reference's field packed into them, and its words of LIGHT's table."""

import time

import numpy as np

from prism.stages.direct.light.model.numbers import F32, LH, PAGE
from prism_reference.indirect.field.pack import PACK_BITS, pack_field
from prism_reference.indirect.field.values import FIELD_SHIFT
from prism_reference.indirect.light import field_for

FIELD_BLOCK = np.array([LH["kFieldBlockX"], LH["kFieldBlockY"], LH["kFieldBlockZ"]])
FIELD_DIRECTION = LH["kFieldDirectionTexels"]


def field_layout(model):
    """The field's dense pages: its blocks along x, y, z (FIELD_BLOCK voxels each, the
    grid padded to whole blocks) and their count, a page a block."""
    blocks = -(-np.asarray(model["field_dims"], dtype=np.int64) // FIELD_BLOCK)
    return blocks, int(np.prod(blocks))


def field_pages(model, texels):
    """The field's texels (voxels, 6) (pack_field) as its pages (pages, 1024) uint32:
    blocks in x, then z, then y; in a block's page the texel of voxel (x, y, z) and
    direction d at d x 128 + (y x 8 + z) x 8 + x; 0 (no data) elsewhere."""
    blocks, count = field_layout(model)
    dims = tuple(int(d) for d in model["field_dims"])
    voxel = np.stack(np.unravel_index(model["field_keys"], dims), -1)
    block, inside = voxel // FIELD_BLOCK, voxel % FIELD_BLOCK
    page = (block[:, 1] * blocks[2] + block[:, 2]) * blocks[0] + block[:, 0]
    across = inside[:, 1] * FIELD_BLOCK[2] + inside[:, 2]
    local = across * FIELD_BLOCK[0] + inside[:, 0]
    pages = np.zeros((count, PAGE * PAGE), dtype=np.uint32)
    direction = np.arange(6) * FIELD_DIRECTION
    pages[page[:, None], direction[None, :] + local[:, None]] = texels
    return pages


def field_of(lights):
    """The field for `lights` (lights["indirect"] names the scene's file) as the card
    holds it: the reference's values (field_for) packed (pack_field) into field_pages.
    A dict: model, pages, scale, seconds."""
    started = time.perf_counter()
    model, values = field_for({**lights, "indirect_packed": False})
    texels, scale = pack_field(values, model["field_has"])
    return {
        "model": model,
        "pages": field_pages(model, texels),
        "scale": scale,
        "seconds": time.perf_counter() - started,
    }


def field_words(words, field, first):
    """The field's words of LIGHT's table (shade.h kLtField*) into `words`: the grid,
    the pages' layout from light page `first` on, the decoding's units."""

    def put(at, values):
        values = np.atleast_1d(np.asarray(values, dtype=F32))
        words[at : at + len(values)] = values.view(np.uint32)

    model = field["model"]
    spacing = F32(model["field_spacing"])
    blocks, count = field_layout(model)
    put(LH["kLtFieldOrigin"], model["field_origin"])
    put(LH["kLtFieldShift"], F32(FIELD_SHIFT) * spacing)
    put(LH["kLtFieldSpacing"], spacing)
    put(LH["kLtFieldInverse"], F32(1) / spacing)
    put(LH["kLtFieldDims"], model["field_dims"])
    put(LH["kLtFieldAcross"], blocks[0])
    put(LH["kLtFieldLayer"], blocks[0] * blocks[2])
    put(LH["kLtFieldFirst"], 1 + first)
    units = [F32(1) / F32((1 << bits) - 1) for bits in PACK_BITS]
    put(LH["kLtFieldUnit"], [(unit * unit) * F32(field["scale"]) for unit in units])
    put(LH["kLtFieldScale"], field["scale"])
    words[LH["kLtFieldPages"]] = count
