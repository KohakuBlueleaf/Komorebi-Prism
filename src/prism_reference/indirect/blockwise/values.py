"""Whole blocks of M = pi F evaluated where they lie: rows and columns are ranges of the
cluster order, so the kernel is broadcast over slices and the rays of many blocks are
traced in one call; the blocks' work on a pool of threads."""

from concurrent.futures import ThreadPoolExecutor

import numpy as np

from prism_reference.indirect.blockwise.pairs import CHUNK
from prism_reference.native.blas import blas_threads
from prism_reference.trace.batch import threads, trace

F = np.float32
ENTRIES = 4 * CHUNK  # block entries evaluated between two traces


def kernel_block(p, n, area, r0, r1, c0, c1):
    """F without visibility (float64, (m, n)) of rows r0:r1 by columns c0:c1, the form
    factor of `form_factors.form_factor_rows`, 0 on the diagonal."""
    d = p[c0:c1][None, :, :] - p[r0:r1][:, None, :]
    r2 = np.einsum("mnk,mnk->mn", d, d)
    r = np.sqrt(np.maximum(r2, 1e-30))
    ci = np.einsum("mnk,mk->mn", d, n[r0:r1]) / r
    cj = -np.einsum("mnk,nk->mn", d, n[c0:c1]) / r
    a = area[c0:c1][None, :]
    top = np.maximum(ci, 0) * np.maximum(cj, 0) * a
    den = np.pi * r2 + a
    value = np.divide(top, den, out=np.zeros_like(top), where=den > 0)
    lo, hi = max(r0, c0), min(r1, c1)
    if lo < hi:
        k = np.arange(lo, hi)
        value[k - r0, k - c0] = 0
    return value


def evaluate(tree, elements, real, eps, r0, r1, c0, c1, each):
    """Calls each(index, block) with every block of M (float64 (m, n)), the kernel by
    slices and `each` on a pool of `batch.threads()` workers (BLAS on one thread each)
    while a batch of ENTRIES traces one any-hit ray a pair of positive kernel. Rays."""
    p = elements["position"].astype(np.float64)
    n = elements["normal"].astype(np.float64)
    area = np.where(real, elements["area"].astype(np.float64), 0.0)
    lift = p + n * eps

    def kernel(b):
        value = kernel_block(p, n, area, r0[b], r1[b], c0[b], c1[b])
        value[~real[r0[b] : r1[b]]] = 0
        live = np.flatnonzero(value > 0)
        o = lift[r0[b] + live // (c1[b] - c0[b])]
        e = lift[c0[b] + live % (c1[b] - c0[b])]
        return value, live, o.astype(F), (e - o).astype(F)

    def finish(b, value, live, blocked):
        value.ravel()[live[blocked]] = 0
        each(b, value * np.pi)

    if not len(r0):
        return 0
    entries = np.cumsum((r1 - r0) * (c1 - c0))
    edges = np.searchsorted(entries, np.arange(ENTRIES, entries[-1], ENTRIES)) + 1
    batches = [ids for ids in np.split(np.arange(len(r0)), edges) if len(ids)]
    rays, finishing = 0, []
    with blas_threads(1), ThreadPoolExecutor(threads()) as pool:
        coming = [pool.submit(kernel, b) for b in batches[0]]
        for k, ids in enumerate(batches):
            done = [job.result() for job in coming]
            for job in finishing:
                job.result()
            if k + 1 < len(batches):
                coming = [pool.submit(kernel, b) for b in batches[k + 1]]
            origin = np.concatenate([o for _, _, o, _ in done])
            direction = np.concatenate([d for _, _, _, d in done])
            _, tri, _, _ = trace(tree, origin, direction, 1.0, any_hit=True)
            rays += len(origin)
            ends = np.cumsum([len(d[1]) for d in done])
            parts = np.split(tri >= 0, ends[:-1])
            finishing = [
                pool.submit(finish, b, value, live, blocked)
                for b, (value, live, _, _), blocked in zip(ids, done, parts)
            ]
        for job in finishing:
            job.result()
    return rays
