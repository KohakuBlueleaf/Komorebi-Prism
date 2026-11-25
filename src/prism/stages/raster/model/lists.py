"""The list pages of every core and its directory page, from the packed records."""

import numpy as np

from prism.stages.raster.model.cost import as_item, band_ranks
from prism.stages.raster.model.numbers import PAGE_SLOTS, PAGE_WORDS, SLOT, K


def build_lists(packed, offsets, members, tiles_of):
    """List pages of all cores and one directory page per core, from packed records,
    the binning's offsets and members, and the items per core (tiles or bands,
    `as_item`): (pages (P, 512) uint32, directory (cores, 1024) uint32)."""
    cores = len(tiles_of)
    if max(len(items) for items in tiles_of) > K["kDirMaxItems"]:
        raise ValueError("a core has more tiles than its directory page holds")
    streams, first_page = [], 0
    directory = np.zeros((cores, K["kDirBytes"] // 4), dtype=np.uint32)
    for core, own_items in enumerate(tiles_of):
        parts, item_ids = [], []
        for item in own_items:
            tile, first_row, end_row = as_item(item)
            tile_ranks = members[offsets[tile] : offsets[tile + 1]]
            band = (first_row, end_row) != (0, 32)
            if band:
                tile_ranks = band_ranks(packed, tile_ranks, tile, first_row, end_row)
            rows_bits = (
                first_row << K["kItemRow0Shift"] | end_row << K["kItemRow1Shift"]
            )
            item_ids.append(tile | (rows_bits if band else 0))
            if len(tile_ranks) == 0:
                item_ids[-1] |= K["kItemEmpty"]
                continue  # an empty tile has no header
            header = np.zeros((1, SLOT), dtype=np.uint32)
            header[0, 0] = K["kMarkTile"]
            header[0, K["kHdrTile"]] = tile
            header[0, K["kHdrCount"]] = len(tile_ranks)
            header[0, K["kHdrRow0"]] = first_row
            header[0, K["kHdrRow1"]] = end_row
            parts += [header, packed[tile_ranks]]
        end_slot = np.zeros((1, SLOT), dtype=np.uint32)
        end_slot[0, 0] = K["kMarkEnd"]
        parts.append(end_slot)
        slots = np.concatenate(parts)
        pad = -len(slots) % PAGE_SLOTS
        slots = np.concatenate([slots, np.zeros((pad, SLOT), dtype=np.uint32)])
        pages = slots.reshape(-1, PAGE_WORDS)
        directory[core, K["kDirFirst"]] = first_page
        directory[core, K["kDirPages"]] = len(pages)
        directory[core, K["kDirItems"]] = len(own_items)
        directory[core, K["kDirIds"] : K["kDirIds"] + len(own_items)] = item_ids
        streams.append(pages)
        first_page += len(pages)
    return np.concatenate(streams), directory
