"""Each core's table: its entries, one a block slice, in pages of 4 KiB."""

from dataclasses import dataclass

import numpy as np

from prism.stages.indirect.transport.plan.deal import row_blocks
from prism.stages.indirect.transport.plan.weights import weight_pages

WORDS = 8  # an entry's words (kernels/apply.h)
HEAD = 8  # a table page's first words: its count, then the core's own range
PAGE_WORDS = 1024  # a table page: 4 KiB
ENTRIES_A_PAGE = (PAGE_WORDS - HEAD) // WORDS


@dataclass
class Tables:
    """Each core's entries ([cores] lists of 8-word rows), its range of receiver tiles
    and its cost; the table tensor's words [cores x pages, PAGE_WORDS]."""

    first: np.ndarray  # [cores + 1] receiver tiles
    entries: list
    pages: int  # table pages a core
    words: np.ndarray
    tiles_read: np.ndarray  # [cores] weight tiles
    x_read: np.ndarray  # [cores] x tiles (each entry its source range)
    zero_entries: int


def tables(s, first, zero_page):
    """Each core's entries, one a block slice (the block's receivers it owns), by the
    block's first source tile, then its rows. A receiver no block reaches gets a zero
    tile's entry, so that every sum is written once."""
    pages_of, _ = weight_pages(s)
    start, blocks = row_blocks(s)
    cores = len(first) - 1
    out, tiles_read, x_read, zeros = [], [], [], 0
    for c in range(cores):
        a, b = int(first[c]), int(first[c + 1])
        mine = np.unique(blocks[start[a] : start[b]])
        mine = mine[np.lexsort((s.row0[mine], s.col0[mine]))]
        rows, read, xs = [], 0, 0
        touched = np.zeros(b - a, bool)
        for q in mine:
            j0, j1 = max(a, s.row0[q]), min(b, s.row1[q])
            k, rank, n = int(s.col1[q] - s.col0[q]), int(s.rank[q]), int(j1 - j0)
            base, skip = int(pages_of[q]), int(j0 - s.row0[q])
            if rank == 0:
                row = (s.col0[q], k, base + skip * k, k * n, 0, 0, j0 - a, 0)
            else:
                u = base + k * rank + skip * rank
                row = (s.col0[q], k, base, k * rank, u, rank * n, j0 - a, rank)
            rows.append(row)
            read += row[3] + row[5]
            xs += k
            touched[j0 - a : j1 - a] = True
        for j in np.flatnonzero(~touched):
            rows.append((0, 1, zero_page, 1, 0, 0, int(j), 0))
            zeros += 1
        out.append(np.array(rows, np.int64).reshape(-1, WORDS))
        tiles_read.append(read)
        x_read.append(xs)
    pages = max(1, max(-(-len(r) // ENTRIES_A_PAGE) for r in out))
    words = np.zeros((cores * pages, PAGE_WORDS), np.uint32)
    for c, rows in enumerate(out):
        for p in range(pages):
            part = rows[p * ENTRIES_A_PAGE : (p + 1) * ENTRIES_A_PAGE]
            page = words[c * pages + p]
            page[0:3] = (len(part), first[c], first[c + 1] - first[c])
            page[HEAD : HEAD + part.size] = part.reshape(-1)
    return Tables(
        first, out, pages, words, np.array(tiles_read), np.array(x_read), zeros
    )
