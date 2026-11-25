"""The numbers a core's buffers are made for, from a set and its tables."""

import numpy as np


def sizes(s, t):
    """The most entries, table pages, own receiver tiles, x's tiles of one entry, rank
    tiles; the weight and x tiles each core reads."""
    own = np.diff(t.first)
    entries = np.array([len(r) for r in t.entries])
    k = s.col1 - s.col0
    return {
        "cores": len(own),
        "entries_most": int(entries.max()),
        "entries_mean": float(entries.mean()),
        "table_pages": t.pages,
        "own_most": int(own.max()),
        "own_least": int(own.min()),
        "k_most": int(k.max()),
        "rank_most": int(s.rank.max()),
        "tiles_read_most": int(t.tiles_read.max()),
        "tiles_read_mean": float(t.tiles_read.mean()),
        "tiles_read_least": int(t.tiles_read.min()),
        "x_read_most": int(t.x_read.max()),
        "x_read_mean": float(t.x_read.mean()),
        "zero_entries": t.zero_entries,
    }
