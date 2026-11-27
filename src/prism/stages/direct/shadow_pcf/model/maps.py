"""The page of maps as the unit's header lays it out: its words, two halves of records
(the whole map's, each fitted map's, each lamp face's), a record's words; a map's levels
as the DEPTH view and the unit leave them (a tile's slot and top, the coarse levels'
pages) and read back. A map is `width` x `height` texels (height None: square)."""

import numpy as np

from prism.core.headers import INCLUDE, defined
from prism.core.resources import lines
from prism.stages.direct.shadow_pcf.model.region import CAMERA_WORDS, H

D = defined(INCLUDE / "thread" / "depth_levels.h")
PAGE = H["SHADOW_PCF_PAGE"]  # a page's texels a row, a tile's
PAGE_BYTES = 4 * PAGE * PAGE
SLOT_BYTES = D["DEPTH_LEVELS_SLOT_BYTES"]  # a tile's levels
TOP_BYTES = D["DEPTH_LEVELS_TOP_BYTES"]  # a tile's top
IN_TILE = D["DEPTH_LEVELS_IN_TILE"]
IN_SLOT = [D[f"DEPTH_LEVELS_L{n}"] for n in range(1, IN_TILE + 1)]  # each level's word
RECORD = H["SHADOW_PCF_RECORD_WORDS"]
WHOLE, FIT = H["SHADOW_PCF_KIND_WHOLE"], H["SHADOW_PCF_KIND_FIT"]
FACE = H["SHADOW_PCF_KIND_FACE"]
F32 = np.float32


def maps_bytes(maps):
    """The page of maps' bytes for `maps` records a half."""
    return 4 * lines(H["SHADOW_PCF_M_RECORDS"] + 2 * maps * RECORD)


def record_at(maps, half, index):
    """The first word of half `half`'s record `index` of `maps` records a half."""
    return H["SHADOW_PCF_M_RECORDS"] + (half * maps + index) * RECORD


def tiles_of(width, height=None):
    """A map's pages across and down (a page a tile)."""
    return width // PAGE, (width if height is None else height) // PAGE


def map_pages(width, height=None):
    """A map's pages, its tiles."""
    across, down = tiles_of(width, height)
    return across * down


def halved(across, down):
    """Each coarser grid of an across x down grid, down to 1 x 1: each side halved,
    rounded up."""
    out = []
    while across > 1 or down > 1:
        across, down = (across + 1) // 2, (down + 1) // 2
        out.append((across, down))
    return out


def coarse_pages(width, height=None):
    """The pages of a map's levels coarser than a tile: a level a page."""
    return len(halved(*tiles_of(width, height)))


def level_count(width, height=None):
    """A map's levels below it, down to 1 x 1: a tile's, then the coarse ones."""
    return IN_TILE + coarse_pages(width, height)


def levels_bytes(sizes):
    """The levels' work bytes for maps of `sizes` [(width, height)] (none: 0): a map's
    tops, a slot and its coarse levels' pages, the most of them."""
    if not sizes:
        return 0
    return max(
        map_pages(w, h) * TOP_BYTES + SLOT_BYTES + coarse_pages(w, h) * PAGE_BYTES
        for w, h in sizes
    )


def record_words(camera, record):
    """A record's words: `camera` (16,) float32, then `record` {name: value} by the
    header's SHADOW_PCF_R_<NAME> (texel and bias as float32)."""
    words = np.zeros(RECORD, dtype=np.uint32)
    words[:CAMERA_WORDS] = np.asarray(camera, F32).view(np.uint32)
    for name, value in record.items():
        at = H[f"SHADOW_PCF_R_{name.upper()}"]
        if name in ("texel", "bias", "margin"):
            words[at] = np.asarray(value, F32).view(np.uint32)
        else:
            words[at] = int(value)
    return words


def maps_words(maps, fit_pages, halves):
    """The page of maps' words: `maps` records a half, the own maps' tensor's pages,
    `halves` two lists of record words."""
    words = np.zeros(maps_bytes(maps) // 4, dtype=np.uint32)
    words[H["SHADOW_PCF_M_MAPS"]] = maps
    words[H["SHADOW_PCF_M_FIT_PAGES"]] = fit_pages
    for half, records in enumerate(halves):
        for index, record in enumerate(records):
            at = record_at(maps, half, index)
            words[at : at + RECORD] = record
    return words


def of_pages(pages, width, height=None):
    """A (height, width) float32 map from its pages (row by row of pages)."""
    across, down = tiles_of(width, height)
    pages = np.asarray(pages, dtype=np.uint32).reshape(down, across, PAGE, PAGE)
    full = pages.transpose(0, 2, 1, 3).reshape(down * PAGE, across * PAGE)
    return np.ascontiguousarray(full).view(F32)


def levels_of(slots, coarse, width, height=None):
    """Each level float32 of a map from its tiles' slots (tiles, words) and its coarse
    levels' pages (pages, words)."""
    across, down = tiles_of(width, height)
    slots = np.asarray(slots, dtype=np.uint32).reshape(down, across, -1)
    out = []
    for n, at in enumerate(IN_SLOT):
        s = 16 >> n
        blocks = slots[:, :, at : at + s * s].reshape(down, across, s, s)
        out.append(blocks.transpose(0, 2, 1, 3).reshape(down * s, across * s).view(F32))
    grids = halved(across, down)
    for page, (a, d) in zip(np.asarray(coarse, dtype=np.uint32), grids, strict=True):
        out.append(np.ascontiguousarray(page.reshape(PAGE, PAGE)[:d, :a]).view(F32))
    return out
