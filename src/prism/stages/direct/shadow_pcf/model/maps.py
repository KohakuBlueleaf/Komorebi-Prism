"""The page of maps as the unit's header lays it out: its words, two halves of records
(the whole map's, then each fitted map's), a record's words; a map's levels as the
DEPTH view and the unit leave them (a tile's slot and top, the coarse levels' pages) and
read back."""

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
F32 = np.float32


def maps_bytes(maps):
    """The page of maps' bytes for `maps` records a half."""
    return 4 * lines(H["SHADOW_PCF_M_RECORDS"] + 2 * maps * RECORD)


def record_at(maps, half, index):
    """The first word of half `half`'s record `index` of `maps` records a half."""
    return H["SHADOW_PCF_M_RECORDS"] + (half * maps + index) * RECORD


def map_pages(side):
    """A map's pages, its tiles."""
    return (side // PAGE) ** 2


def level_count(side):
    """A map's levels below it: side / 2 down to 1."""
    return int(side).bit_length() - 1


def coarse_pages(side):
    """The pages of a map's levels coarser than a tile: a level a page."""
    return level_count(side // PAGE)


def levels_bytes(sides):
    """The levels' work bytes for maps of `sides` (none: 0): a map's tops, a slot and
    its coarse levels' pages, the most of them."""
    if not sides:
        return 0
    return max(
        map_pages(s) * TOP_BYTES + SLOT_BYTES + coarse_pages(s) * PAGE_BYTES
        for s in sides
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


def maps_words(maps, grid, tiles, fit_pages, halves):
    """The page of maps' words: `maps` records a half, a fitted view's `grid` word and
    `tiles`, the fitted tensor's pages, `halves` two lists of record words."""
    words = np.zeros(maps_bytes(maps) // 4, dtype=np.uint32)
    words[H["SHADOW_PCF_M_MAPS"]] = maps
    words[H["SHADOW_PCF_M_GRID"]] = grid
    words[H["SHADOW_PCF_M_TILES"]] = tiles
    words[H["SHADOW_PCF_M_FIT_PAGES"]] = fit_pages
    for half, records in enumerate(halves):
        for index, record in enumerate(records):
            at = record_at(maps, half, index)
            words[at : at + RECORD] = record
    return words


def of_pages(pages, side):
    """A (side, side) float32 map from its pages (row by row of pages)."""
    across = max(1, side // PAGE)
    pages = np.asarray(pages, dtype=np.uint32).reshape(across, across, PAGE, PAGE)
    full = pages.transpose(0, 2, 1, 3).reshape(across * PAGE, across * PAGE)
    return np.ascontiguousarray(full[:side, :side]).view(F32)


def levels_of(slots, coarse, side):
    """Each level (s, s) float32 of a map of `side` from its tiles' slots (tiles, words)
    and its coarse levels' pages (pages, words)."""
    across = side // PAGE
    slots = np.asarray(slots, dtype=np.uint32).reshape(across, across, -1)
    out = []
    for n, at in enumerate(IN_SLOT):
        s = 16 >> n
        blocks = slots[:, :, at : at + s * s].reshape(across, across, s, s)
        out.append(
            blocks.transpose(0, 2, 1, 3).reshape(across * s, across * s).view(F32)
        )
    g = across
    for page in np.asarray(coarse, dtype=np.uint32):
        g //= 2
        out.append(np.ascontiguousarray(page.reshape(PAGE, PAGE)[:g, :g]).view(F32))
    return out
