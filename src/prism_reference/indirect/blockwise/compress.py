"""A whole block's low-rank form by a randomized range grown a tile of columns at a time
(one power step each, only its numerically new directions) until the new directions'
largest value is below the tolerance; the small factor's values from its Gram matrix."""

import numpy as np

# Columns the range grows by (one tile) and the seed of its random test matrices.
SKETCH, SKETCH_SEED = 32, 71
# A powered sketch's direction is new above KEEP x tolerance^3 of the first one's largest
# value (one power step cubes the singular values).
KEEP = 1e-3


def top_value(b):
    """The largest singular value of a short matrix b (r, n), from its Gram matrix."""
    return float(np.sqrt(max(np.linalg.eigvalsh(b @ b.T)[-1], 0.0)))


def exact_factors(a, tolerance):
    """As `sketch_factors` from the block's full singular values."""
    left, sigma, right = np.linalg.svd(a, full_matrices=False)
    if sigma[0] <= 0:
        return None
    k = int((sigma > tolerance * sigma[0]).sum())
    if k * sum(a.shape) >= a.size:
        return None
    root = np.sqrt(sigma[:k])
    return left[:, :k] * root, right[:k].T * root


def sketch_factors(block, tolerance):
    """U (m, k), V (n, k) float64 with sigma^(1/2) each, the singular values of the
    block above `tolerance` times the largest; None when the block is zero or k (m + n)
    >= m n. A range that would pass m n / (m + n) columns: `exact_factors`."""
    a = np.asarray(block, np.float64)
    m, n = a.shape
    rng = np.random.default_rng(SKETCH_SEED)
    q = np.zeros((m, 0))
    largest = scale = 0.0
    while True:
        if (q.shape[1] + SKETCH) * (m + n) >= m * n:
            return exact_factors(a, tolerance)
        y = a @ (a.T @ (a @ rng.standard_normal((n, SKETCH))))
        for _ in range(2):
            y -= q @ (q.T @ y)
        u, s, _ = np.linalg.svd(y, full_matrices=False)
        scale = scale or s[0]
        tile = u[:, s > KEEP * tolerance**3 * scale]
        if scale <= 0 or not tile.shape[1]:
            break
        size = top_value(tile.T @ a)
        largest = largest or size
        q = np.concatenate([q, tile], axis=1)
        if size <= tolerance * largest:
            break
    if not q.shape[1]:
        return None
    small = q.T @ a
    power, left = np.linalg.eigh(small @ small.T)
    sigma = np.sqrt(np.maximum(power[::-1], 0))
    left = left[:, ::-1]
    k = int((sigma > tolerance * sigma[0]).sum())
    if k * (m + n) >= m * n:
        return None
    root = np.sqrt(sigma[:k])
    right = small.T @ left[:, :k] / sigma[:k]
    return (q @ left[:, :k]) * root, right * root
