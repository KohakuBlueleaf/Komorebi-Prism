"""w: every block's tiles in bfp8_b, stored transposed, one block after another; its
pages laid out, encoded and decoded."""

import numpy as np
from komorebi import formats

from prism_common.formats import TILE, format_of

WEIGHT_FORMAT = format_of("bfp8_b")
CHUNK = 1 << 16  # tiles encoded or decoded at a time


def weight_pages(s):
    """Each block's first page in w and the pages in all (with one zero tile at the
    end). A dense block's K x N tiles column by column (tile (k, j) at page j K + k); a
    low-rank block's V (K x R) column by column, then its U^T (R x N) so."""
    k = s.col1 - s.col0
    n = s.row1 - s.row0
    size = np.where(s.rank == 0, k * n, k * s.rank + s.rank * n)
    first = np.concatenate([[0], np.cumsum(size)])
    return first[:-1], int(first[-1]) + 1


def weight_tiles(s, start, count):
    """Pages start .. start + count of w as [count, 32, 32] float32 (each tile as the
    product x W takes it: rows the sources, columns the receivers)."""
    pages_of, _ = weight_pages(s)
    numbers = s.weights()
    out = np.zeros((count, TILE, TILE), np.float32)
    first = np.searchsorted(pages_of, start, side="right") - 1
    for q in range(max(first, 0), s.blocks):
        base = int(pages_of[q])
        if base >= start + count:
            break
        k, n, rank = (
            int(s.col1[q] - s.col0[q]),
            int(s.row1[q] - s.row0[q]),
            int(s.rank[q]),
        )
        parts = []
        if rank == 0:
            parts.append((int(s.offset_a[q]), k, n))
        else:
            parts.append((int(s.offset_a[q]), k, rank))
            parts.append((int(s.offset_b[q]), rank, n))
        tiles = []
        for offset, rows, cols in parts:
            m = np.asarray(numbers[offset : offset + rows * cols * TILE * TILE])
            m = m.reshape(rows, TILE, cols, TILE).transpose(2, 0, 1, 3)
            tiles.append(m.reshape(-1, TILE, TILE))  # column by column
        tiles = np.concatenate(tiles)
        lo, hi = max(base, start), min(base + len(tiles), start + count)
        if lo < hi:
            out[lo - start : hi - start] = tiles[lo - base : hi - base]
    return out


def encode_weights(s):
    """w's bytes [pages, 1088] uint8: bfp8_b of tiles stored transposed (the turned
    product's weight)."""
    _, total = weight_pages(s)
    raw = np.zeros((total, WEIGHT_FORMAT.tile_bytes), np.uint8)
    for start in range(0, total, CHUNK):
        count = min(CHUNK, total - start)
        tiles = weight_tiles(s, start, count)
        data, _ = formats.to_bytes(tiles, WEIGHT_FORMAT.komorebi, "tile", turned=True)
        raw[start : start + count] = data.reshape(count, WEIGHT_FORMAT.tile_bytes)
    return raw


def decode_weights(raw):
    """The values the card multiplies: [pages, 32, 32] float32 as x W takes them."""
    out = np.zeros((len(raw), TILE, TILE), np.float32)
    for start in range(0, len(raw), CHUNK):
        part = np.asarray(raw[start : start + CHUNK])
        values = formats.from_bytes(
            part, (len(part), TILE, TILE), WEIGHT_FORMAT.komorebi, "tile"
        )
        out[start : start + len(part)] = formats.transposed_tiles(values)
    return out
