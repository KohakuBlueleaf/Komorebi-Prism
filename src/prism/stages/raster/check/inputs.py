"""A scene's inputs for the pass and frame checks, from the host model at the default
frame's tiles: the counters, histograms, middle pass, items region, prefixes and ranges;
and the idle thread that holds the regions the commands read and write."""

from pathlib import Path

import numpy as np

from prism.stages.raster.model import count, middle, numbers

K, S = numbers.K, numbers.S
CUT_LEAST = 256  # HIST's tiles when none is heavy: the first that have entries
CLUSTER = 1  # the X280 cluster of the raster's thread
IDLE = Path(__file__).resolve().parent / "idle.c"  # a thread that returns at once


def with_thread(program, regions):
    """`program` with the idle thread on the raster's cluster holding `regions`."""
    program.thread(cluster=CLUSTER, sources=[IDLE], regions=regions, deadline=10.0)
    return program


def ranges_of(blocks, cores, form):
    """A valid range set (first, end) a core: "even" the even partition; "a" (or
    "b") uneven, the cores' shares growing (or shrinking) with their number."""
    if form == "even":  # the model's partition, in integers
        edges = count.partitions(blocks, cores)
        return np.stack([edges[:-1], edges[1:]], axis=1).astype(np.uint32)
    share = (np.arange(cores + 1) / cores) ** 2
    if form == "b":
        share = 1 - share[::-1]
    edges = np.floor(blocks * share).astype(np.int64)
    edges[0], edges[-1] = 0, blocks
    return np.stack([edges[:-1], edges[1:]], axis=1).astype(np.uint32)


def layout(mid, totals):
    """Per item its core and header slot, per core its first page, pages, items and
    end slot: the middle pass's list layout (model.middle's)."""
    item_index = {item: i for i, item in enumerate(mid["items"])}
    core_of = np.zeros(len(mid["items"]), dtype=np.int64)
    header = np.zeros(len(mid["items"]), dtype=np.int64)
    core_words, first_page = [], 0
    for core, own in enumerate(mid["tiles_of"]):
        slot = 16 * first_page
        for item in own:
            i = item_index[item]
            core_of[i] = core
            if totals[i]:
                header[i] = slot
                slot += 1 + int(totals[i])
        pages = -(-(slot + 1 - 16 * first_page) // numbers.PAGE_SLOTS)
        core_words.append((first_page, pages, len(own), slot))
        first_page += pages
    return core_of, header, np.asarray(core_words, dtype=np.uint32)


def items_region(host, mid, totals, heavy, hprefix_address):
    """The items region the thread's middle pass leaves (setup.h): the items table,
    the base words, HSUM's pages' address, the frame, item and core words."""
    sizes = host.sizes
    region = np.zeros(-(-sizes["kItemsRegionBytes"] // 4096) * 1024, dtype=np.uint32)
    table = middle.item_table(mid["items"], sizes["kTiles"], sizes["kItems"])
    region[: len(table)] = table
    core_of, header, core_words = layout(mid, totals)
    heavy_index = {tile: i + 1 for i, (tile, _) in enumerate(heavy)}
    base = np.where(totals > 0, header + 1, 0).astype(np.uint32)
    band = [heavy_index.get(tile, 0) for tile, _, _ in mid["items"]]
    base |= np.asarray(band, dtype=np.uint32) << S["kBaseSlotBits"]
    at = sizes["kBaseAt"] // 4
    region[at : at + len(base)] = base
    region[sizes["kHprefixAddrAt"] // 4] = hprefix_address
    at = sizes["kFrameWordsAt"] // 4
    region[at : at + 16] = host.frame_words()
    item_words = np.stack(
        [core_of | totals.astype(np.int64) << 8, np.where(totals > 0, header, 0)],
        axis=1,
    )
    at = sizes["kItemWordsAt"] // 4
    region[at : at + item_words.size] = item_words.reshape(-1)
    at = sizes["kCoreWordsAt"] // 4
    region[at : at + core_words.size] = core_words.reshape(-1)
    return region
