"""The apply as the card computes it, on the host: x and t in bfloat16, every product
exact, sums in float64."""

import numpy as np
from komorebi import formats

from prism.stages.indirect.transport.plan.weights import weight_pages
from prism_common.formats import TILE


def x_tiles(x):
    """x [N, 3] as the [32, N] row of tiles the card reads (colours as rows 0 to 2)."""
    row = np.zeros((TILE, len(x)), np.float32)
    row[:3] = x.T
    return row


def bf16(values):
    """Rounded to bfloat16 (nearest, ties to even), as float32."""
    return formats.bf16_values(formats.bf16_bits(np.asarray(values, np.float32)))


def emulate(s, w, x):
    """y [N, 3] as the card computes it from the decoded weights w [pages, 32, 32]: x
    and t in bfloat16, every product exact, sums in float64 (the card's in float32)."""
    pages_of, _ = weight_pages(s)
    xr = bf16(x_tiles(x)).astype(np.float64)[:3]  # [3, N]
    y = np.zeros((3, s.tiles * TILE))
    for q in range(s.blocks):
        k, n, rank = (
            int(s.col1[q] - s.col0[q]),
            int(s.row1[q] - s.row0[q]),
            int(s.rank[q]),
        )
        base = int(pages_of[q])
        src = xr[:, s.col0[q] * TILE : s.col1[q] * TILE]
        dst = slice(s.row0[q] * TILE, s.row1[q] * TILE)

        def matrix(at, rows, cols):
            t = w[at : at + rows * cols].reshape(cols, rows, TILE, TILE)
            return t.transpose(1, 2, 0, 3).reshape(rows * TILE, cols * TILE)

        if rank == 0:
            y[:, dst] += src @ matrix(base, k, n)
        else:
            t = bf16(src @ matrix(base, k, rank)).astype(np.float64)
            y[:, dst] += t @ matrix(base + k * rank, rank, n)
    return y.T.astype(np.float32)
