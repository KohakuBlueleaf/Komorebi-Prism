"""The elements' form factors with visibility: rows of F, and the whole F built by
strips into a memory-mapped file."""

import time

import numpy as np
from numpy.lib.format import open_memmap

from prism_reference.trace.batch import trace

F = np.float32
STRIP = 128  # rows of F a strip of the build


def form_factor_rows(tree, elements, rows, eps):
    """F (len(rows), N) float32 with visibility (an any-hit ray between the points moved
    eps along their normals), near field clamped as a disc; and the rays traced."""
    p = elements["position"].astype(np.float64)
    n = elements["normal"].astype(np.float64)
    area = elements["area"].astype(np.float64)
    count = len(p)
    i = np.repeat(rows, count)
    j = np.tile(np.arange(count), len(rows))
    d = p[j] - p[i]
    r2 = np.einsum("ij,ij->i", d, d)
    r = np.sqrt(np.maximum(r2, 1e-30))
    ci = np.einsum("ij,ij->i", n[i], d) / r
    cj = -np.einsum("ij,ij->i", n[j], d) / r
    value = np.maximum(ci, 0) * np.maximum(cj, 0) * area[j] / (np.pi * r2 + area[j])
    value[i == j] = 0
    live = np.nonzero(value > 0)[0]
    if len(live):
        o = p[i[live]] + n[i[live]] * eps
        e = p[j[live]] + n[j[live]] * eps
        _, tri, _, _ = trace(tree, o, e - o, 1.0, any_hit=True)
        value[live[tri >= 0]] = 0
    return value.reshape(len(rows), count).astype(F), len(live)


def dense_form_factors(tree, elements, eps, folder, log=print):
    """The whole F (N, N) float32 as a memmap <folder>/F.npy, by strips of STRIP rows;
    a stopped build goes on from the strips done when the elements are the same."""
    folder.mkdir(parents=True, exist_ok=True)
    count = len(elements["position"])
    path, done_path = folder / "F.npy", folder / "F_rows.npy"
    same = (folder / "F_elements.npz").exists() and path.exists() and done_path.exists()
    if same:
        with np.load(folder / "F_elements.npz") as f:
            same = all(np.array_equal(f[k], elements[k]) for k in elements)
    if same:
        matrix, done = open_memmap(path, mode="r+"), np.load(done_path)
    else:
        np.savez(folder / "F_elements.npz", **elements)
        matrix = open_memmap(path, mode="w+", dtype=F, shape=(count, count))
        done = np.zeros(-(-count // STRIP), dtype=bool)
    started, rays = time.perf_counter(), 0
    for s in np.nonzero(~done)[0]:
        rows = np.arange(s * STRIP, min(count, (s + 1) * STRIP))
        matrix[rows], traced = form_factor_rows(tree, elements, rows, eps)
        rays += traced
        done[s] = True
        if s % 20 == 19 or s == len(done) - 1:
            matrix.flush()
            np.save(done_path, done)
            seconds = time.perf_counter() - started
            log(f"F strip {s + 1}/{len(done)}: {rays} rays, {seconds:.0f} s")
    matrix.flush()
    np.save(done_path, done)
    return matrix, rays
