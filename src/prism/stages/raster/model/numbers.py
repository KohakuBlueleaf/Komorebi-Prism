"""The raster stage's numbers: its headers' constants and the sizes that follow a capacity."""

from pathlib import Path

from prism.core.headers import INCLUDE, constexpr, defined
from prism_reference.raster.fill import TILES_X, TILES_Y

STAGE = Path(__file__).resolve().parent.parent
KERNELS = STAGE / "kernels"
THREAD = STAGE / "thread"
K = constexpr(KERNELS / "raster.h")
S = constexpr(KERNELS / "setup.h")
GRID = constexpr(INCLUDE / "grid.h")
M = defined(THREAD / "raster_middle.h")

TILES = TILES_X * TILES_Y
SLOT = K["kSlotWords"]
PAGE_SLOTS = K["kSlotsPerPage"]
PAGE_WORDS = SLOT * PAGE_SLOTS
NEG_ZERO_NEIGHBOUR = 0x80000001
LANES = 32
BLOCK_SLOTS = S["kBlockSlots"]
BLOCK_WORDS = BLOCK_SLOTS * LANES
GROUPS = M["RM_GROUPS"]
SPLIT = M["RM_SPLIT"]
MAX_BANDS = M["RM_MAX_BANDS"]
# a camera area (setup.h): the view's page (the camera, the view's words; the grid
# word's place), then a page a core (its range at words 0 and 1, its costs after)
AREA_PAGE = S["kAreaPageBytes"]
AREA_PAGES = S["kAreaPages"]
AREA_COSTS_AT = S["kAreaCostsAt"]
VIEW_AT = S["kViewAt"]
VIEW_GRID = S["kViewGrid"]


def sizes(tiles, recount, heavy, band_items):
    """setup.h's sizes that follow a capacity's `tiles`, its `heavy` tiles and
    `band_items`; `recount`: the histograms of the heavy tiles only."""
    items = tiles + band_items
    out = {
        "kTiles": tiles,
        "kBandItems": band_items,
        "kHeavyMax": heavy,
        "kHprefixPageBytes": 128 * heavy,
        "kItems": items,
        "kCountBytes": 8 * tiles,
        "kSlotsBytes": 4 * items,
        "kItemsBytes": 4 * tiles + 2 * items,
        "kItemRows": 4 * tiles,
        "kSumsHeavyAt": 8 * tiles,
    }
    out["kBaseAt"] = out["kItemsBytes"]
    out["kHprefixAddrAt"] = out["kBaseAt"] + 4 * items
    out["kShadeAddrAt"] = out["kHprefixAddrAt"] + 4
    out["kFrameWordsAt"] = out["kHprefixAddrAt"] + 64
    out["kItemWordsAt"] = out["kFrameWordsAt"] + 64
    out["kCoreWordsAt"] = out["kItemWordsAt"] + 4 * S["kItemWords"] * items
    out["kItemsRegionBytes"] = (
        out["kCoreWordsAt"] + S["kCoreWords"] * 4 * S["kMaxFillCores"]
    )
    out["kHistBytes"] = max(
        64 * (heavy if recount else tiles),
        out["kItemsRegionBytes"] + S["kDirPageBytes"] + 128 + S["kOutBytes"],
        out["kHprefixAddrAt"] - out["kBaseAt"] + 64 + out["kHprefixPageBytes"],
    )
    return out
