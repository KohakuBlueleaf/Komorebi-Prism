"""The raster class's sizes: the numbers of its fields and items, from setup.h and
grid.h, and those that follow a frame's capacity."""

import math

from prism.core import fields
from prism.stages.raster import capacity
from prism.stages.raster.model import numbers

K, S = numbers.K, numbers.S
PAGE = 4096  # a region's page, and a tile field's
PLANES = K["kPlanes"]  # an item's planes (pages)
WORK_WORDS = S["kWorkBytes"] // 4  # the pack thread's space
PASS_OUT_PAGES = S["kOutPages"]  # COUNT's and SETUP's records, pack to mover B
SPROF_WORDS = S["kSProfBytes"] // 4  # the passes' profile words (two passes)
OUT_PAGES = K["kOutPages"]  # FILL's output pages
DIR_FRAME = K["kDirFrame"]  # a directory page's frame words
DIR_IDS = K["kDirIds"]  # a directory page's items
SLOT_BYTES = K["kSlotWords"] * 4  # a list slot
VIEW_WORD = numbers.VIEW_AT // 4 + numbers.VIEW_GRID  # the view page's grid word
AREA_ITEMS = numbers.AREA_PAGE // 64  # 64 B items a camera area page (the camera's 1st)
COSTS_ITEM = numbers.AREA_COSTS_AT // 64  # a core's page's costs (two items)
# SUM: the counters' and prefixes' items moved 32 at a time
SUM_BLOCK = 32
# SUM: a slice's two totals (entries, rows) in one block
TOTALS_BLOCK = 2
# HSUM: the histograms' and prefixes' items moved 16 at a time
HSUM_BLOCK = 16


def capacity_constants(held=None):
    """The class's sizes that follow a capacity `held` (None: the default frame's)."""
    heavy, band_items = capacity.heavy_capacity(held)
    tiles = numbers.TILES if held is None else held.tiles
    recount = held is not None and held.recount
    sizes = numbers.sizes(tiles, recount, heavy, band_items)
    high_first = sizes["kFrameWordsAt"] // PAGE
    return {
        "COUNTER_WORDS": sizes["kCountBytes"] // 4,
        "KEPT_HIST_WORDS": sizes["kHistBytes"] // 4,
        "SLOT_WORDS": sizes["kSlotsBytes"] // 4,
        "TILE_OF_WORDS": -(-2 * sizes["kItems"] // 16) * 4,
        "COUNTER_ITEMS": sizes["kCountBytes"] // 64,
        "SLOT_ITEMS": sizes["kSlotsBytes"] // 64,
        "ROW_ITEMS": 4 * tiles // 64,
        "HEAVY_ITEMS": heavy,
        "ITEM_WORDS": sizes["kItemsBytes"] // 4,
        "LOW_PAGES": math.ceil(sizes["kItemsBytes"] / PAGE),
        "HIGH_FIRST": high_first,
        "HIGH_PAGES": math.ceil(sizes["kItemsRegionBytes"] / PAGE) - high_first,
    }


DEFAULT = capacity_constants()


# the common fields' needs (prism.core.fields): the command space's parts in bytes
for part, words in (
    ("raster_counters", "COUNTER_WORDS"),
    ("kept_hist", "KEPT_HIST_WORDS"),
):
    fields.need(part, "raster", lambda held, w=words: 4 * capacity_constants(held)[w])
fields.need("out_ring", "raster", lambda held: OUT_PAGES)
