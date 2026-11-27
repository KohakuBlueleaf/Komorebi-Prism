"""What the middle pass between COUNT and SETUP gives: list pages, directory, next slots,
and SETUP's items page."""

import numpy as np

from prism.stages.raster.model.cost import assign, cost_of
from prism.stages.raster.model.numbers import PAGE_SLOTS, PAGE_WORDS, SLOT, K


def middle(counts, rows, cores, mode="balanced", bands=None):
    """The middle pass from the counters and, for bands, `items_of`'s result: items to
    cores by cost, the list pages with headers and end slots, the directory, each setup
    core's next slot per item (setup cores, items), the items in tile order, the slots.
    """
    if bands is None:
        items = [(tile, 0, 32) for tile in range(counts.shape[1])]
        per_core, cost = counts, cost_of(counts, rows)
    else:
        items, per_core, cost = bands
    total = per_core.sum(axis=0)
    partition = assign(cost, cores, mode)
    header = np.full(len(items), -1, dtype=np.int64)
    directory = np.zeros((cores, K["kDirBytes"] // 4), dtype=np.uint32)
    marks, first_page = [], 0
    for core, own in enumerate(partition):
        slot = 16 * first_page
        item_ids = []
        for item in own:
            tile, first_row, end_row = items[item]
            band = (first_row, end_row) != (0, 32)
            rows_bits = (
                first_row << K["kItemRow0Shift"] | end_row << K["kItemRow1Shift"]
            )
            item_ids.append(tile | (rows_bits if band else 0))
            if total[item] == 0:
                item_ids[-1] |= K["kItemEmpty"]
                continue
            header[item] = slot
            marks.append((slot, K["kMarkTile"], tile, total[item], first_row, end_row))
            slot += 1 + total[item]
        marks.append((slot, K["kMarkEnd"], 0, 0, 0, 0))
        pages = -(-(slot + 1 - 16 * first_page) // PAGE_SLOTS)
        directory[core, K["kDirFirst"]] = first_page
        directory[core, K["kDirPages"]] = pages
        directory[core, K["kDirItems"]] = len(own)
        directory[core, K["kDirIds"] : K["kDirIds"] + len(own)] = item_ids
        first_page += pages
    slots = np.zeros((first_page * PAGE_SLOTS, SLOT), dtype=np.uint32)
    for slot, mark, tile, count, first_row, end_row in marks:
        slots[slot, 0] = mark
        if mark == K["kMarkTile"]:
            slots[slot, K["kHdrTile"]] = tile
            slots[slot, K["kHdrCount"]] = count
            slots[slot, K["kHdrRow0"]] = first_row
            slots[slot, K["kHdrRow1"]] = end_row
    before = np.cumsum(per_core, axis=0) - per_core
    next_slots = np.where(header >= 0, header + 1, 0)[None, :] + before
    return {
        "tiles_of": [[items[item] for item in own] for own in partition],
        "items": items,
        "pages": slots.reshape(-1, PAGE_WORDS),
        "directory": directory,
        "next": next_slots.astype(np.uint32),
        "slots": len(slots),
    }


def item_table(items, tiles, capacity):
    """SETUP's items page for a frame of `tiles` tiles and `capacity` items: per tile
    its first item and their number, then per item its rows (uint16)."""
    table = np.zeros(tiles + -(-capacity // 2), dtype=np.uint32)
    first = np.array([tile for tile, _, _ in items])
    first_item = np.searchsorted(first, np.arange(tiles))
    counts = np.bincount(first, minlength=tiles)
    table[:tiles] = first_item | counts << 16
    rows = table[tiles:].view(np.uint16)
    rows[: len(items)] = [first_row | end_row << 8 for _, first_row, end_row in items]
    return table
