"""The matrix as blocks in the card's layout: dense near blocks, low-rank admissible
ones from their singular values, and the counts of what is stored."""

import time

import numpy as np

from prism_reference.indirect.hmatrix.cluster import ETA, UNIT, partition

F = np.float32
TOLERANCE = 1e-2  # singular values kept above this times the largest


def hierarchical(matrix, tree, tolerance=TOLERANCE, eta=ETA, log=print):
    """The matrix as blocks in the card's layout (y_row = x_row @ W), zero blocks
    dropped: dense n x m, or V (n x kp) then U^T (kp x m) with sigma^(1/2) each, kp a
    multiple of 32. Blocks dict, weights."""
    admissible, near = partition(tree, eta)
    start, end = tree["start"], tree["end"]
    rows = []
    for a, b in near:
        block = matrix[start[a] : end[a], start[b] : end[b]]
        if block.any():
            rows.append(
                (start[a], end[a], start[b], end[b], 0, 0, block.T.copy(), None)
            )
    near_count = len(rows)
    r0, r1 = start[admissible[:, 0]], end[admissible[:, 0]]
    c0, c1 = start[admissible[:, 1]], end[admissible[:, 1]]
    shapes = sorted(set(zip((r1 - r0).tolist(), (c1 - c0).tolist())), key=np.prod)
    started = time.perf_counter()
    found = {}
    for m, n in shapes:
        group = np.nonzero((r1 - r0 == m) & (c1 - c0 == n))[0]
        per = max(1, 40_000_000 // (m * n))
        for s in range(0, len(group), per):
            ids = group[s : s + per]
            stack = np.stack([matrix[r0[i] : r1[i], c0[i] : c1[i]] for i in ids])
            live = stack.reshape(len(ids), -1).any(axis=1)
            if not live.any():
                continue
            stack = stack[live]
            u, sigma, vt = np.linalg.svd(stack, full_matrices=False)
            for q, i in enumerate(ids[live]):
                k = int((sigma[q] > tolerance * sigma[q][0]).sum())
                if m * n < k * (m + n):
                    found[i] = (0, 0, stack[q].T.copy(), None)
                    continue
                root = np.sqrt(sigma[q][:k])
                kp = -(-k // UNIT) * UNIT
                v = np.zeros((n, kp), F)
                v[:, :k] = vt[q][:k].T * root
                ut = np.zeros((kp, m), F)
                ut[:k] = (u[q][:, :k] * root).T
                found[i] = (1, k, v, ut)
        if m * n >= 256 * 256:
            seconds = time.perf_counter() - started
            log(f"SVD {m} x {n}: {len(group)} blocks, {seconds:.0f} s")
    rows += [(r0[i], r1[i], c0[i], c1[i], *found[i]) for i in sorted(found)]
    return pack(rows, near_count)


def pack(rows, near_count):
    """Blocks dict and weights of block rows (r0, r1, c0, c1, kind, rank, A, B): A the
    dense Wt or V, B U^T or None; the first `near_count` rows are the near blocks."""
    kind = np.array([row[4] for row in rows], dtype=np.int8)
    rank = np.array([row[5] for row in rows], dtype=np.int32)
    sizes = [row[6].size + (0 if row[7] is None else row[7].size) for row in rows]
    offset_a = np.concatenate([[0], np.cumsum(sizes)[:-1]]).astype(np.int64)
    weights = np.empty(int(np.sum(sizes)), F)
    for row, a in zip(rows, offset_a):
        weights[a : a + row[6].size] = row[6].ravel()
        if row[7] is not None:
            weights[a + row[6].size : a + row[6].size + row[7].size] = row[7].ravel()
    m_of = np.array([row[1] - row[0] for row in rows], dtype=np.int64)
    n_of = np.array([row[3] - row[2] for row in rows], dtype=np.int64)
    padded = (-(-rank // UNIT) * UNIT).astype(np.int32)
    blocks = {
        "row0": np.array([row[0] for row in rows], dtype=np.int32),
        "row1": np.array([row[1] for row in rows], dtype=np.int32),
        "col0": np.array([row[2] for row in rows], dtype=np.int32),
        "col1": np.array([row[3] for row in rows], dtype=np.int32),
        "kind": kind,
        "rank": rank,
        "rank_padded": padded,
        "offset_a": offset_a,
        "offset_b": offset_a + np.where(kind == 1, n_of * padded, m_of * n_of),
        "scale": np.ones(len(rows), F),
        "near": np.arange(len(rows)) < near_count,
    }
    return blocks, weights


def matrix_counts(blocks):
    """Blocks, tiles and numbers of the stored matrix."""
    m = (blocks["row1"] - blocks["row0"]).astype(np.int64)
    n = (blocks["col1"] - blocks["col0"]).astype(np.int64)
    lr = blocks["kind"] == 1
    kp = blocks["rank_padded"].astype(np.int64)
    tiles = np.where(
        lr, (kp // UNIT) * (m // UNIT + n // UNIT), (m // UNIT) * (n // UNIT)
    )
    return {
        "blocks": len(lr),
        "blocks_low_rank": int(lr.sum()),
        "blocks_dense_near": int(blocks["near"].sum()),
        "blocks_dense_admissible": int((~lr & ~blocks["near"]).sum()),
        "rank_median": float(np.median(blocks["rank"][lr])) if lr.any() else 0.0,
        "tiles": int(tiles.sum()),
        "tiles_dense": int(tiles[~lr].sum()),
        "tiles_low_rank": int(tiles[lr].sum()),
    }
