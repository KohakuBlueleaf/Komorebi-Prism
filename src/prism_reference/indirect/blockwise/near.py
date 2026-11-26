"""Dense blocks from their own pairs only: the near blocks, and admissible blocks that
are cheaper whole; with a symmetric kernel each pair of mirrored blocks is one."""

import numpy as np

from prism_reference.indirect.blockwise.values import evaluate

F = np.float32


def dense_blocks(tree, elements, real, eps, r0, r1, c0, c1):
    """Each block of M = pi F (float32 (m, n) arrays) and the rays traced."""
    out = [None] * len(r0)

    def keep(b, block):
        out[b] = block.astype(F)

    rays = evaluate(tree, elements, real, eps, r0, r1, c0, c1, keep)
    return out, rays


def mirrored(a, b, symmetric):
    """For node pairs (a, b): which to evaluate and, per pair, the evaluated pair whose
    transpose it is (itself when evaluated)."""
    if not symmetric:
        every = np.arange(len(a))
        return every, every
    key = {(int(x), int(y)): k for k, (x, y) in enumerate(zip(a, b))}
    source = np.array([key[(min(x, y), max(x, y))] for x, y in zip(a, b)])
    return np.nonzero(a <= b)[0], source


def near_blocks(tree, elements, real, eps, cluster, pairs, symmetric):
    """The near blocks (node pairs (k, 2)) as M's dense blocks, each from its own pairs;
    with `symmetric`, (b, a) is the transpose of (a, b). Blocks and rays."""
    start, end = cluster["start"], cluster["end"]
    a, b = pairs[:, 0], pairs[:, 1]
    todo, source = mirrored(a, b, symmetric)
    done, rays = dense_blocks(
        tree,
        elements,
        real,
        eps,
        start[a[todo]],
        end[a[todo]],
        start[b[todo]],
        end[b[todo]],
    )
    at = np.full(len(a), -1)
    at[todo] = np.arange(len(todo))
    blocks = []
    for k in range(len(a)):
        block = done[at[source[k]]]
        blocks.append(block if source[k] == k else block.T)
    return blocks, rays
