"""The cluster tree of whole element units and the partition of the matrix into
admissible and near blocks."""

import numpy as np

UNIT = 32  # elements a unit
LEAF_UNITS = 8  # units a leaf holds at most
ETA = 1.0  # admissible when the separation is at least this


def separation(tree, a, b):
    """Distance between the boxes of nodes a and b over the larger box diagonal."""
    lo, hi = tree["lo"], tree["hi"]
    gap = np.maximum(0, np.maximum(lo[a] - hi[b], lo[b] - hi[a]))
    diagonal = np.maximum(
        np.linalg.norm(hi[a] - lo[a], axis=-1), np.linalg.norm(hi[b] - lo[b], axis=-1)
    )
    return np.linalg.norm(gap, axis=-1) / np.maximum(diagonal, 1e-9)


def cluster_tree(position, leaf_units=LEAF_UNITS):
    """A binary tree of whole UNIT-element units: a node cuts its longest box axis at
    half its units (stable sort). Order `perm` and per node start, end, children, box.
    """
    count = len(position)
    perm = np.arange(count)
    nodes = []

    def make(start, end):
        k = len(nodes)
        nodes.append([start, end, -1, -1])
        units = (end - start) // UNIT
        if units > leaf_units:
            idx = perm[start:end]
            p = position[idx]
            axis = int(np.argmax(p.max(0) - p.min(0)))
            perm[start:end] = idx[np.argsort(p[:, axis], kind="stable")]
            middle = start + (units // 2) * UNIT
            nodes[k][2] = make(start, middle)
            nodes[k][3] = make(middle, end)
        return k

    make(0, count)
    nodes = np.array(nodes, dtype=np.int64)
    p = position.astype(np.float64)
    lo = np.array([p[perm[s:e]].min(0) for s, e in nodes[:, :2]])
    hi = np.array([p[perm[s:e]].max(0) for s, e in nodes[:, :2]])
    return {"perm": perm, "start": nodes[:, 0], "end": nodes[:, 1]} | {
        "child": nodes[:, 2:4],
        "lo": lo,
        "hi": hi,
    }


def partition(tree, eta=ETA):
    """Node pairs (a, b) from (root, root): admissible when separation >= eta; two
    leaves a near block; one leaf: the other's two children; else the four pairs."""
    admissible, near = [], []
    a, b = np.array([0]), np.array([0])
    child = tree["child"]
    while len(a):
        ok = separation(tree, a, b) >= eta
        admissible.append(np.stack([a[ok], b[ok]], 1))
        a, b = a[~ok], b[~ok]
        la, lb = child[a, 0] < 0, child[b, 0] < 0
        near.append(np.stack([a[la & lb], b[la & lb]], 1))
        pairs = []
        m = la & ~lb
        pairs += [(a[m], child[b[m], 0]), (a[m], child[b[m], 1])]
        m = ~la & lb
        pairs += [(child[a[m], 0], b[m]), (child[a[m], 1], b[m])]
        m = ~la & ~lb
        pairs += [(child[a[m], i], child[b[m], j]) for i in (0, 1) for j in (0, 1)]
        a = np.concatenate([p[0] for p in pairs])
        b = np.concatenate([p[1] for p in pairs])
    return np.concatenate(admissible), np.concatenate(near)
