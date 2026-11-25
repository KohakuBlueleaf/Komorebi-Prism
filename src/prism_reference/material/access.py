"""The texels SHADE reads over a frame: per pixel its reads by texture page, and the
counts a shading pass is sized by (distinct values per tile, a page cache's hits)."""

from collections import OrderedDict

import numpy as np

from prism_reference.material.kinds import (
    ALBEDO,
    FLAT,
    LIT,
    MASK,
    MASKED,
    NORMAL,
    SPECULAR,
)
from prism_reference.material.texture import texel_xy
from prism_reference.raster.fill import TILES_X, TILES_Y
from prism_reference.raster.frames import (
    nearer_layer,
    pixel_values,
    shade_layer,
    shade_setup,
)
from prism_reference.scene.frame import HEIGHT, TILE, WIDTH
from prism_reference.scene.public.textures import MIP_LEVELS

PAGE = 32  # a texture page: 32 x 32 texels of one level, 4 KB
CACHE_PAGES = (8, 16, 32)


def layer_accesses(scene, materials, prepared, layer, ys, xs):
    """(pixel, page, texel) of every texel SHADE reads at pixels (ys, xs) of a layer,
    in slot order per pixel; page and texel are numbers unique in the frame."""
    t = layer["tri"][ys, xs]
    m = materials["material"][t]
    kind = materials["kind"][m]
    _, _, _, u, v, _ = pixel_values(layer, prepared, ys, xs)
    texture = materials["textures"][m]
    reads = {
        ALBEDO: kind != FLAT,
        MASK: kind == MASKED,
        NORMAL: (kind == LIT) & prepared["frame_ok"][t],
        SPECULAR: kind == LIT,
    }
    out = []
    pixel = ys * WIDTH + xs
    for slot, wanted in reads.items():
        take = wanted & (texture[:, slot] >= 0)
        if not take.any():
            continue
        tex = texture[take, slot]
        level = prepared["level"][t[take], slot]
        x, y, entry = texel_xy(materials, tex, level, u[take], v[take])
        pages_across = (entry[:, 1] + PAGE - 1) // PAGE
        level_key = tex.astype(np.int64) * MIP_LEVELS + level
        page = (level_key << 24) | ((y // PAGE) * pages_across + x // PAGE)
        texel = entry[:, 0] // 4 + y * entry[:, 1] + x
        out.append((pixel[take], slot, page, texel))
    return out


def frame_accesses(scene, materials, layers):
    """Per pixel the kinds SHADE runs and the texels it reads: the masked layer where
    it is nearer (and, at a hole, then the other layer), else the other layer."""
    prepared = shade_setup(scene, materials)
    opaque, masked = layers["opaque"], layers["masked"]
    first = nearer_layer(masked, opaque)
    _, hole = shade_layer(scene, materials, prepared, masked)
    second = (~first | hole) & (opaque["tri"] >= 0)
    kinds = np.zeros((HEIGHT, WIDTH), dtype=np.int32)
    accesses = []
    for layer, where in ((masked, first), (opaque, second)):
        ys, xs = np.nonzero(where)
        kind = materials["kind"][materials["material"][layer["tri"][ys, xs]]]
        kinds[ys, xs] |= 1 << kind
        accesses += layer_accesses(scene, materials, prepared, layer, ys, xs)
    pixel = np.concatenate([a[0] for a in accesses])
    # Per pixel: the masked layer's reads first, then the other's, slot by slot.
    order = np.argsort(pixel, kind="stable")
    page = np.concatenate([a[2] for a in accesses])[order]
    texel = np.concatenate([a[3] for a in accesses])[order]
    return kinds, pixel[order], page, texel


def histogram(values):
    """{value: how many} of integer values."""
    counts = np.bincount(np.asarray(values, dtype=np.int64))
    return {int(k): int(n) for k, n in enumerate(counts) if n}


def per_tile_distinct(values, valid):
    """Distinct values per 32 x 32 tile (H, W) over the valid pixels."""
    tiles = TILES_Y * TILES_X
    y, x = np.nonzero(valid)
    tile = (y // TILE) * TILES_X + x // TILE
    pairs = np.unique(np.stack([tile, values[y, x]], 1), axis=0)
    return np.bincount(pairs[:, 0], minlength=tiles)


def lru_hits(stream, size):
    """Hits of an LRU cache of `size` pages over a stream of page numbers."""
    cache, hits = OrderedDict(), 0
    for page in stream:
        if page in cache:
            hits += 1
            cache.move_to_end(page)
        else:
            cache[page] = True
            if len(cache) > size:
                cache.popitem(last=False)
    return hits
