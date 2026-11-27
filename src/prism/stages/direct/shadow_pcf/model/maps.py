"""The page of maps as the unit's header lays it out: its words, two halves of records
(the whole map's, then each fitted map's), a record's words; the fitted maps' pages and
the levels' pages; the levels read back."""

import numpy as np

from prism.core.resources import lines
from prism.stages.direct.shadow_pcf.model.region import CAMERA_WORDS, H

PAGE = H["SHADOW_PCF_PAGE"]  # a page's texels a row
PAGE_BYTES = 4 * PAGE * PAGE
PIECE_PAGES = H["SHADOW_PCF_PIECE_PAGES"]  # a piece of a map reduced at once, a side
RECORD = H["SHADOW_PCF_RECORD_WORDS"]
WHOLE, FIT = H["SHADOW_PCF_KIND_WHOLE"], H["SHADOW_PCF_KIND_FIT"]
F32 = np.float32


def maps_bytes(maps):
    """The page of maps' bytes for `maps` records a half."""
    return 4 * lines(H["SHADOW_PCF_M_RECORDS"] + 2 * maps * RECORD)


def record_at(maps, half, index):
    """The first word of half `half`'s record `index` of `maps` records a half."""
    return H["SHADOW_PCF_M_RECORDS"] + (half * maps + index) * RECORD


def level_sides(side):
    """The sides of a map's levels: side / 2 down to 1."""
    out, s = [], side // 2
    while s >= 1:
        out.append(s)
        s //= 2
    return out


def level_across(side):
    """A level's pages a row."""
    return max(1, side // PAGE)


def levels_pages(side):
    """The pages of every level of a map of `side`."""
    return sum(level_across(s) ** 2 for s in level_sides(side))


def map_pages(side):
    """A map's pages."""
    return (side // PAGE) ** 2


def levels_bytes(sides):
    """The levels region's bytes for maps of `sides` (none: 0): a piece and the largest
    map's levels."""
    if not sides:
        return 0
    piece = min(max(sides) // PAGE, PIECE_PAGES) ** 2
    return PAGE_BYTES * (piece + max(levels_pages(s) for s in sides))


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
    across = level_across(side)
    pages = np.asarray(pages, dtype=np.uint32).reshape(across, across, PAGE, PAGE)
    full = pages.transpose(0, 2, 1, 3).reshape(across * PAGE, across * PAGE)
    return np.ascontiguousarray(full[:side, :side]).view(F32)


def levels_of_pages(pages, side):
    """Each level (s, s) float32 of a map of `side` from its levels' pages."""
    out, at = [], 0
    for s in level_sides(side):
        count = level_across(s) ** 2
        out.append(of_pages(pages[at : at + count], s))
        at += count
    return out
