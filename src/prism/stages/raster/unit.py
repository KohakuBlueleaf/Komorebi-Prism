"""The raster stage's thread unit: its C, its regions' bytes from the host's capacity, its
numbers, the layer's columns, its times and results, and its build definitions."""

import re

from prism.core.unit import Region, Unit
from prism.stages.raster import capacity
from prism.stages.raster.model import numbers

K, S = numbers.K, numbers.S
# setup.h's numbers the unit's C reads, as RASTER_K_<NAME> (those that follow the
# capacity from numbers.sizes)
SETUP_NUMBERS = (
    "kAreaPages",
    "kAreaPageBytes",
    "kAreaCostsAt",
    "kViewAt",
    "kViewGrid",
    "kViewDepth",
    "kCamWords",
    "kCostKnots",
    "kSetupPrefix",
    "kHeavyBytes",
)
SIZE_NUMBERS = (
    "kItems",
    "kSlotsBytes",
    "kItemRows",
    "kBaseAt",
    "kHprefixAddrAt",
    "kShadeAddrAt",
    "kFrameWordsAt",
    "kItemWordsAt",
    "kCoreWordsAt",
)
FRAMES = tuple(f"frame_{i}" for i in range(K["kDirFrameMax"]))  # the frame's tensors


def macro_of(name):
    """setup.h's `kItemWordsAt` as `RASTER_K_ITEM_WORDS_AT`."""
    return "RASTER_K_" + re.sub(r"(?<!^)(?=[A-Z])", "_", name[1:]).upper()


def defines(host):
    """The unit's -D definitions for the host's capacity: the kernels' capacity defines,
    the middle pass's (RM_*), setup.h's numbers and the histograms' page bytes."""
    heavy, band_items = capacity.heavy_capacity(host.held)
    out = dict(capacity.capacity_defines(host.held))
    out |= {
        "RM_TILES": f"{host.held.tiles}u",
        "RM_MAX_HEAVY": f"{heavy}u",
        "RM_BAND_ITEMS": f"{band_items}u",
        "RASTER_K_HIST_PAGE_BYTES": f"{4 * numbers.GROUPS * heavy}u",
        "RASTER_K_SLICE_TILES": f"{numbers.GRID['kSliceTiles']}u",
    }
    out |= {macro_of(name): f"{S[name]}u" for name in SETUP_NUMBERS}
    out |= {macro_of(name): f"{host.sizes[name]}u" for name in SIZE_NUMBERS}
    return out


def camera_bytes(host, areas):
    """The camera region: an area a (view, layer), the view's page and a page a core."""
    return areas * numbers.AREA_PAGES * numbers.AREA_PAGE


def items_bytes(host):
    """The items region: SETUP's items page, the base words, PLACE's words."""
    page = numbers.AREA_PAGE
    return -(-host.sizes["kItemsRegionBytes"] // page) * page


UNIT = Unit(
    sources=(
        "thread/raster_unit.c",
        "thread/raster_ranges.c",
        "thread/raster_middle.c",
    ),
    includes=("thread",),
    setup=True,
    layer=True,
    regions={
        "camera": Region(camera_bytes, by_area=True),
        "heavy": Region(S["kHeavyBytes"]),
        "items": Region(items_bytes),
        "work": Region(
            lambda host, areas: capacity.work_bytes(host.held, areas), by_area=True
        ),
        "sums": Region(lambda host: capacity.sums_bytes(host.held)),
    },
    numbers=("balance", "steps"),
    columns=(
        "mesh",
        "blocks",
        "lists",
        "list_slots",
        "directory",
        "profile",
        "fill_profile",
        "shade",
        "frame_pages",
    )
    + FRAMES,
    shares={
        "frame.visibility": ("directory", "frame_pages") + FRAMES,
        "frame.lists": ("directory", "lists"),
    },
    times=(
        "count",
        "sum",
        "take",
        "heavy",
        "hist",
        "hsum",
        "cut",
        "sort",
        "assign",
        "compact",
        "pages",
        "give",
        "middle",
        "place",
        "setup",
        "fill",
    ),
    results=("slots", "items", "marks", "heavy_tiles"),
    defines=defines,
)
