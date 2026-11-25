"""The apply y = M x of the stored blocks, block after block."""

import numpy as np

F = np.float32
BLOCK_KEYS = ("row0", "row1", "col0", "col1", "kind", "rank_padded", "offset_a")
BLOCK_KEYS += ("offset_b", "scale")


def apply(blocks, weights, x, left=None):
    """y = M x (N, C) float32 from the blocks, block after block; `left` rounds the left
    operand (x's and t's rows) as the card."""
    y = np.zeros(x.shape, dtype=F)
    xq = (left(x) if left else x).astype(F)
    for r0, r1, c0, c1, kd, kp, oa, ob, s in zip(*(blocks[k] for k in BLOCK_KEYS)):
        m, n, xr = r1 - r0, c1 - c0, xq[c0:c1].T
        if kd == 0:
            y[r0:r1] += ((xr @ weights[oa : oa + n * m].reshape(n, m)) * s).T
            continue
        t = xr @ weights[oa : oa + n * kp].reshape(n, kp)
        if left:
            t = left(t)
        y[r0:r1] += ((t @ weights[ob : ob + kp * m].reshape(kp, m)) * s).T
    return y
