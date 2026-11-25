"""The receiver tiles dealt to the cores in contiguous ranges, the largest cost least."""

import numpy as np


def row_blocks(s):
    """For each receiver tile, the blocks whose rows hold it: (start [T + 1],
    blocks)."""
    n = s.row1 - s.row0
    blocks = np.repeat(np.arange(s.blocks), n)
    rows = np.concatenate([np.arange(a, b) for a, b in zip(s.row0, s.row1)])
    order = np.argsort(rows, kind="stable")
    start = np.searchsorted(rows[order], np.arange(s.tiles + 1))
    return start, blocks[order]


def deal(s, cores):
    """Contiguous ranges of receiver tiles, one a core, the largest cost least: a
    range's cost is the weight tiles its slices read (a dense slice K n, a low-rank
    one its own V, K R, and its U^T columns, R n). Returns first [cores + 1]."""
    start, blocks = row_blocks(s)
    k = s.col1 - s.col0
    per_row = np.where(s.rank == 0, k, s.rank)  # a receiver's tiles of each block

    def ranges(cap):
        firsts, a, cost, touched = [0], 0, 0, set()
        for r in range(s.tiles):
            here = blocks[start[r] : start[r + 1]]
            add = int(per_row[here].sum())
            add += sum(int(k[q] * s.rank[q]) for q in here if q not in touched)
            if cost + add > cap and r > a:
                firsts.append(r)
                if len(firsts) > cores:
                    return None
                a, cost, touched = r, 0, set()
                add = int(per_row[here].sum()) + int((k[here] * s.rank[here]).sum())
            cost += add
            touched.update(int(q) for q in here if s.rank[q])
        return firsts + [s.tiles] * (cores + 1 - len(firsts))

    low, high = 1, int((k * (s.row1 - s.row0) + k * s.rank).sum())
    while low < high:
        cap = (low + high) // 2
        if ranges(cap) is None:
            low = cap + 1
        else:
            high = cap
    return np.array(ranges(low))
