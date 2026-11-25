"""The raster stage's numbers that follow a capacity: the heavy tiles' and bands' tables,
the kernels' build defines, the sums region's bytes, the frame tensors' pages."""

from prism.stages.raster.model.numbers import GROUPS, SPLIT, TILES, K, M, S

# the base word's heavy index field: 1 + index below 2^(32 - kBaseSlotBits)
HEAVY_FIELD = 1 << (32 - S["kBaseSlotBits"])
# the host-stepped passes' tables (no fill cores given)
STEPPED_HEAVY, STEPPED_BAND_ITEMS = 256, 1024
# frame pages per tensor at the least
CHUNK_PAGES = 510
PAGE = 4096  # a thread region's page
# the thread's own region at the least (the 1,024-tile frame's)
WORK_LEAST = 256 << 10


def heavy_capacity(held=None):
    """(heavy tiles, bands' items) the tables of a capacity `held` hold: `cores` / SPLIT
    and one, the heavy at most its tiles, the items to 32; without cores the
    host-stepped passes'. ValueError past the base word's heavy index field."""
    if held is None or held.cores is None:
        return STEPPED_HEAVY, STEPPED_BAND_ITEMS
    most = int(held.cores / SPLIT) + 1
    heavy = min(held.tiles, most)
    if heavy >= HEAVY_FIELD:
        raise ValueError(
            f"{held.cores} fill cores can cut {heavy} heavy tiles: the base word's "
            f"heavy index holds {HEAVY_FIELD - 1} (kernels/setup.h kBaseSlotBits), "
            f"at most {int((HEAVY_FIELD - 2) * SPLIT)} cores"
        )
    return heavy, -(-most // 32) * 32


def capacity_defines(held=None):
    """The kernels' build defines of a capacity `held` (None: the default frame's
    tiles): RASTER_TILES, RASTER_HEAVY, RASTER_BAND_ITEMS, and RASTER_WIDE,
    RASTER_RECOUNT when set."""
    heavy, band_items = heavy_capacity(held)
    counts = {"RASTER_HEAVY": str(heavy), "RASTER_BAND_ITEMS": str(band_items)}
    if held is None:
        return {"RASTER_TILES": str(TILES), **counts}
    return {
        "RASTER_TILES": str(held.tiles),
        **counts,
        **({"RASTER_WIDE": "1"} if held.wide else {}),
        **({"RASTER_RECOUNT": "1"} if held.recount else {}),
    }


def sums_bytes(held=None):
    """The bytes of the sums region of a capacity `held`: SUM's entries and rows, 8 a
    tile, then HSUM's 32 counts a heavy tile, 128 bytes each."""
    tiles = TILES if held is None else held.tiles
    return 8 * tiles + 128 * heavy_capacity(held)[0]


def chunk_pages(pages):
    """Pages per tensor of a frame of `pages`: CHUNK_PAGES, or as many more (a multiple
    of 15) as keep it in the kDirFrameMax tensors the directory names."""
    most = K["kDirFrameMax"]
    if -(-pages // CHUNK_PAGES) <= most:
        return CHUNK_PAGES
    each = -(-pages // most)  # pages a tensor, then up to a multiple of 15
    return -(-each // 15) * 15


def work_bytes(held, areas):
    """The thread's own region of a capacity `held` with `areas` camera areas (its
    work_t): 32 B a tile, 60 B an item, a fixed part (heavy tiles' counts, cores, the
    areas' ranges) and a page to spare; whole pages, at least WORK_LEAST."""
    tiles, (heavy, band_items) = held.tiles, heavy_capacity(held)
    items = tiles + band_items
    cores = M["RM_MAX_CORES"]
    fixed = (
        8 * 2 * cores  # load, heap
        + 4 * (cores + 1)  # first_item
        + 8 * heavy * 2 * GROUPS  # histograms
        + 4 * 2 * cores  # slot_counts, item_counts
        + 4 * (1 + 2 * heavy)  # tile_item's last, heavy, bands
        + 4 * (areas + 1) * (cores + 1)  # ranges, cuts
    )
    total = 32 * tiles + 60 * items + fixed + PAGE
    return max(-(-total // PAGE) * PAGE, WORK_LEAST)
