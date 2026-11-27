"""A file's view transform as the card holds it: the cube's pages in bricks, the
region's words, and the post step's conversion through those pages in numpy (the
pages a tile asks for, the values against prism_reference.post.view)."""

import math
from pathlib import Path

import numpy as np

from prism.core.headers import constexpr
from prism_reference.post.view import ENTRY_ONE, LOG_TABLE, coordinates

KERNELS = Path(__file__).resolve().parent.parent / "kernels"
VIEW = constexpr(KERNELS / "view.h")
F = np.float32
NODES, CELLS = VIEW["kViewBrickNodes"], VIEW["kViewBrickCells"]
PAGE_WORDS = VIEW["kViewPageBytes"] // 4
ENTRY_WORDS = VIEW["kViewEntryBytes"] // 4
REGION_WORDS = VIEW["kViewRegionBytes"] // 4
LOG_AT = VIEW["kViewLogAt"]
TILE = 32  # a tile's pixels a side


def across(cube):
    """Bricks an axis of a cube of n nodes an axis."""
    return math.ceil((cube.shape[0] - 1) / CELLS)


def brick_pages(cube):
    """The cube's pages (bricks^3, PAGE_WORDS) uint32: brick (x, y, z) at page
    x + a (y + a z), its node (r, g, b) at entry (b 8 + g) 8 + r (nodes past the cube
    repeat its last)."""
    n, a = cube.shape[0], across(cube)
    local = np.arange(NODES)
    pages = np.zeros((a, a, a, NODES, NODES, NODES, ENTRY_WORDS), np.uint32)
    for z in range(a):
        for y in range(a):
            for x in range(a):
                r, g, b = (np.minimum(c * CELLS + local, n - 1) for c in (x, y, z))
                block = cube[np.ix_(r, g, b)].astype(np.uint32)  # [r, g, b, 3]
                block = block.transpose(2, 1, 0, 3)  # [b, g, r, 3]
                pages[z, y, x, ..., 0] = block[..., 0] | block[..., 1] << 16
                pages[z, y, x, ..., 1] = block[..., 2]
    return pages.reshape(a**3, PAGE_WORDS)


def region_words(view, base):
    """The view's words (after the thresholds in the region `show_table`): on, cells,
    bricks across, the pages' bank address, low, scale, 2^low, 2^high, the matrix;
    the log2 table."""
    words = np.zeros(REGION_WORDS, np.uint32)
    if view is None or view["cube"] is None:
        return words
    cells = view["cube"].shape[0] - 1
    if cells > VIEW["kViewCellsMost"]:
        raise ValueError(
            f"a cube of {cells} cells; the card takes {VIEW['kViewCellsMost']}"
        )
    low, high = view["low"], view["high"]
    floats = [low, cells / (high - low), 2.0**low, 2.0**high]
    words[VIEW["kViewOn"]] = 1
    words[VIEW["kViewCells"]] = cells
    words[VIEW["kViewAcross"]] = across(view["cube"])
    words[VIEW["kViewBase"]] = base
    at = VIEW["kViewLow"]
    words[at : at + 4] = np.array(floats, F).view(np.uint32)
    at = VIEW["kViewMatrix"]
    words[at : at + 9] = view["matrix"].astype(F).ravel().view(np.uint32)
    words[LOG_AT : LOG_AT + len(LOG_TABLE)] = LOG_TABLE.view(np.uint32)
    return words


def card_values(view, pages, colour):
    """The values (..., 3) the post step gives the thresholds, from the cube's pages
    as it addresses them: each pixel's brick, its cell's corners in that page."""
    cube = view["cube"]
    a = across(cube)
    c = coordinates(view, colour)
    i = np.minimum(c.astype(np.int64), cube.shape[0] - 2)
    f = (c - i.astype(F)).astype(F)
    brick = (i * VIEW["kViewSevenths"]) >> VIEW["kViewSeventhsShift"]
    page = brick[..., 0] + a * (brick[..., 1] + a * brick[..., 2])
    node = i - brick * CELLS
    fr, fg, fb = f[..., 0], f[..., 1], f[..., 2]
    first_r = (fr >= fg) & (fr >= fb)
    first_g = ~first_r & (fg >= fb)
    second_g = np.where(first_r, fg >= fb, False)
    second_r = np.where(first_g, fr >= fb, np.where(first_r, False, fr >= fg))
    unit = np.eye(3, dtype=np.int64)
    first = np.where(
        first_r[..., None], unit[0], np.where(first_g[..., None], unit[1], unit[2])
    )
    second_axis = np.where(
        first_r,
        np.where(second_g, 1, 2),
        np.where(first_g, np.where(second_r, 0, 2), np.where(second_r, 0, 1)),
    )
    second = unit[second_axis]
    fa = np.sum(f * first, -1, dtype=F)
    fb_ = np.sum(f * second, -1, dtype=F)
    fc = np.sum(f * (1 - first - second), -1, dtype=F)
    corners = (node, node + first, node + first + second, node + 1)
    weights = (F(1) - fa, fa - fb_, fb_ - fc, fc)
    total = None
    for corner, weight in zip(corners, weights, strict=True):
        entry = (corner[..., 2] * NODES + corner[..., 1]) * NODES + corner[..., 0]
        word = entry * ENTRY_WORDS
        rg, blue = pages[page, word], pages[page, word + 1]
        values = np.stack([rg & 0xFFFF, rg >> 16, blue & 0xFFFF], -1).astype(F)
        term = weight[..., None] * values
        total = term if total is None else total + term
    return total * F(1.0 / ENTRY_ONE), page


def window_order(tile):
    """A tile's (32, 32) values in the planes' window order (1024,): row r, column c
    at 64 (r / 2) + r % 2 + 16 (c / 8) + 2 (c % 8)."""
    r, c = np.meshgrid(np.arange(TILE), np.arange(TILE), indexing="ij")
    at = 64 * (r // 2) + r % 2 + 16 * (c // 8) + 2 * (c % 8)
    out = np.empty(TILE * TILE, tile.dtype)
    out[at.ravel()] = tile.ravel()
    return out


def item_asks(pages, slots=VIEW["kViewSlots"], chunk=16):
    """(passes, pages asked) of an item whose pixels' pages are `pages` in window
    order: parts of `chunk` taken while their distinct pages fit `slots`."""
    passes, asked, held = 0, 0, set()
    for at in range(0, len(pages), chunk):
        part = set(pages[at : at + chunk].tolist())
        if len(held | part) > slots:
            passes, asked, held = passes + 1, asked + len(held), set()
        held |= part
    return passes + 1, asked + len(held)


def frame_asks(page, size, slots=VIEW["kViewSlots"]):
    """Each whole 32 x 32 tile's (passes, pages asked) of a frame's pixels' pages."""
    h, w = size
    return np.array(
        [
            item_asks(window_order(page[y : y + TILE, x : x + TILE]), slots)
            for y in range(0, h, TILE)
            for x in range(0, w, TILE)
        ]
    )


def tile_pages(page, size):
    """The distinct cube pages each 32 x 32 tile of a frame (H, W) of pixels' pages
    asks for."""
    h, w = size
    counts = []
    for y in range(0, h, TILE):
        for x in range(0, w, TILE):
            counts.append(len(np.unique(page[y : y + TILE, x : x + TILE])))
    return np.array(counts)
