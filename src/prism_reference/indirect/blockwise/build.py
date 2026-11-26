"""Building a scene's indirect model without the dense matrix: near blocks from their own
pairs, admissible blocks by cross approximation, then the same files as the dense build.
"""

import time
from pathlib import Path

import numpy as np

from prism_reference.direct.lights import load
from prism_reference.indirect.blockwise.compress import sketch_factors
from prism_reference.indirect.blockwise.far import cross_blocks, recompress
from prism_reference.indirect.blockwise.near import dense_blocks, mirrored, near_blocks
from prism_reference.indirect.blockwise.pairs import facing_any
from prism_reference.indirect.blockwise.values import evaluate
from prism_reference.indirect.elements import (
    ELEMENTS,
    PROBE_DEAD,
    padded,
    probe,
    sample_elements,
    subset,
)
from prism_reference.indirect.field.build import build_field, field_counts
from prism_reference.indirect.files import transport_dir, write
from prism_reference.indirect.hmatrix.apply import apply
from prism_reference.indirect.hmatrix.card import card_apply
from prism_reference.indirect.hmatrix.cluster import ETA, UNIT, cluster_tree, partition
from prism_reference.indirect.hmatrix.compress import TOLERANCE, matrix_counts, pack
from prism_reference.indirect.light import element_light
from prism_reference.indirect.sky import transfer
from prism_reference.material.kinds import TRANSPARENT
from prism_reference.scene.public.materials import load_materials
from prism_reference.scene.public.mesh import load_mesh
from prism_reference.scene.public.table import table
from prism_reference.scene.public.views import EPS_SCALE
from prism_reference.trace.tree import build as build_tree
from prism_reference.trace.tree import load_tree

F = np.float32


def low_rank_row(u, v):
    """The stored (kind, rank, A, B) of M_block ~ U V^T: dense Wt when m n < k (m + n),
    else V (n, kp) and U^T (kp, m) zero padded to kp a multiple of UNIT."""
    (m, k), n = u.shape, len(v)
    if m * n < k * (m + n):
        return 0, 0, (u @ v.T).T.astype(F), None
    kp = -(-k // UNIT) * UNIT
    a = np.zeros((n, kp), F)
    a[:, :k] = v
    b = np.zeros((kp, m), F)
    b[:k] = u.T
    return 1, k, a, b


def cross_found(tree, elements, real, eps, r0, r1, c0, c1, tolerance, log):
    """Per block (U, V), (dense, None) or None (zero) by cross approximation; the rays
    and the steps."""
    factors, rays, steps = cross_blocks(
        tree, elements, real, eps, r0, r1, c0, c1, tolerance
    )
    whole = np.array([f is None for f in factors], dtype=bool)
    log(f"cross: {len(r0)} blocks, {steps} steps, {whole.sum()} whole, {rays} rays")
    full, traced = dense_blocks(
        tree, elements, real, eps, r0[whole], r1[whole], c0[whole], c1[whole]
    )
    dense = iter(full)
    found = []
    for f in factors:
        if f is None:
            block = next(dense)
            found.append((block, None) if block.any() else None)
        else:
            found.append(recompress(*f, tolerance))
    return found, rays + traced, steps


def sketch_found(tree, elements, real, eps, r0, r1, c0, c1, tolerance, log):
    """Per block (U, V), (dense, None) or None (zero) from all its pairs, each block
    compressed by `sketch_factors` as soon as it is evaluated; the rays and 0 steps."""
    found = [None] * len(r0)

    def keep(b, block):
        if block.any():
            f = sketch_factors(block, tolerance)
            found[b] = (block.astype(F), None) if f is None else f

    rays = evaluate(tree, elements, real, eps, r0, r1, c0, c1, keep)
    return found, rays, 0


METHODS = {"cross": cross_found, "sketch": sketch_found}


def far_rows(
    tree, elements, real, eps, cluster, pairs, symmetric, method, tolerance, log
):
    """Per admissible node pair its stored (kind, rank, A, B) or None when zero, the
    rays and the cross steps; with `symmetric`, (b, a) from (a, b) transposed."""
    start, end = cluster["start"], cluster["end"]
    a, b = pairs[:, 0], pairs[:, 1]
    todo, source = mirrored(a, b, symmetric)
    r0, r1, c0, c1 = start[a[todo]], end[a[todo]], start[b[todo]], end[b[todo]]
    done, rays, steps = METHODS[method](
        tree, elements, real, eps, r0, r1, c0, c1, tolerance, log
    )
    found = dict(zip(todo.tolist(), done))
    rows = []
    for k in range(len(a)):
        f = found[int(source[k])]
        if f is None:
            rows.append(None)
        elif f[1] is None:
            block = f[0] if source[k] == k else f[0].T
            rows.append((0, 0, block.T.astype(F), None))
        else:
            rows.append(low_rank_row(*(f if source[k] == k else f[::-1])))
    return rows, rays, steps


def ray_tree(name, data, mesh, materials, split):
    """The ray tree with glass open, built once: a view's saved tree when the scene has
    no glass and one is kept, else `trace.tree.build` with `split` over the others."""
    glass = materials["kind"][materials["material"]] == TRANSPARENT
    if not glass.any():
        for view in table()[name]["views"]:
            path = Path(data) / f"{name}_{view}_tree.npz"
            if path.exists():
                tree = load_tree(path)
                if len(tree["leaf_tri"]) == len(mesh["indices"]):
                    return {k: np.ascontiguousarray(v) for k, v in tree.items()}
    keep = np.nonzero(~glass)[0]
    tree = build_tree(
        {"positions": mesh["positions"], "indices": mesh["indices"][keep]}, split
    )
    tree["leaf_tri"] = keep[tree["leaf_tri"]].astype(np.int32)
    return {k: np.ascontiguousarray(v) for k, v in tree.items()}


def build(
    name,
    data,
    log=print,
    method="sketch",
    far_only=False,
    tolerance=TOLERANCE,
    split="presorted",
):
    """The indirect files as `indirect.build.build` writes them, the blocks computed
    directly by `method` (METHODS; no dense F, no y_exact), the ray tree by `split`;
    `far_only` stores no near block. The counts."""
    entry = table()[name]["lighting"]
    mesh, _ = load_mesh(name, data)
    materials, _ = load_materials(name, data)
    lights = load(name, data)
    times, counts, clock = {}, {}, [time.perf_counter()]

    def step(label):
        now = time.perf_counter()
        times[label] = round(now - clock[0], 1)
        clock[0] = now
        log(f"{name}: {label} {times[label]} s")

    tree = ray_tree(name, data, mesh, materials, split)
    p = mesh["positions"].astype(np.float64)
    eps = EPS_SCALE * float(np.linalg.norm(p.max(0) - p.min(0)))
    step("tree")
    sampled, spacing = sample_elements(mesh, materials, entry.get("elements", ELEMENTS))
    step("sample")
    escape, near = probe(tree, sampled, eps)
    live = subset(sampled, escape + near <= PROBE_DEAD)
    counts |= {
        "sampled": len(escape),
        "probe_dead": int((escape + near > PROBE_DEAD).sum()),
    }
    step("probe")
    keep = np.nonzero(facing_any(live["position"], live["normal"]))[0]
    counts["empty_rows"] = int(len(live["position"]) - len(keep))
    count = -(-len(keep) // UNIT) * UNIT
    elements, real = padded(subset(live, keep), count)
    cluster = cluster_tree(elements["position"])
    perm = cluster["perm"]
    elements, real = subset(elements, perm), real[perm]
    source = np.where(real, keep[np.minimum(perm, len(keep) - 1)], -1)
    admissible, near_pairs = partition(cluster, ETA)
    area = elements["area"][real]
    symmetric = bool(len(area) and (area == area[0]).all())
    counts |= {"kept": int(real.sum()), "elements": count, "spacing": spacing}
    counts |= {"eps": eps, "symmetric": symmetric}
    step("order")
    start, end = cluster["start"], cluster["end"]
    rows, rays = [], 0
    if not far_only:
        blocks, rays = near_blocks(
            tree, elements, real, eps, cluster, near_pairs, symmetric
        )
        for (a, b), block in zip(near_pairs, blocks):
            if block.any():
                rows.append((start[a], end[a], start[b], end[b], 0, 0, block.T.copy()))
                rows[-1] += (None,)
    near_count = len(rows)
    counts["near_rays"] = rays
    step("near")
    far, rays, steps = far_rows(
        tree,
        elements,
        real,
        eps,
        cluster,
        admissible,
        symmetric,
        method,
        tolerance,
        log,
    )
    for (a, b), row in zip(admissible, far):
        if row is not None:
            rows.append((start[a], end[a], start[b], end[b], *row))
    counts |= {"far_rays": rays, "cross_steps": steps, "method": method}
    blocks, weights = pack(rows, near_count)
    step("far")
    model = elements | {"real": real, "blocks": blocks, "weights": weights}
    model["transfer"] = np.where(real[:, None], transfer(tree, elements, eps), F(0))
    step("transfer")
    model |= build_field(elements["position"][real], elements["normal"][real], spacing)
    model["field_columns"] = np.nonzero(real)[0][model["field_columns"]].astype(
        np.int32
    )
    step("field")
    x = element_light(lights, model)["l0"]
    result = {
        "x": x,
        "y_float": apply(blocks, weights, x),
        "y_q8": card_apply(blocks, weights, x),
    }
    step("checks")
    counts |= matrix_counts(blocks) | field_counts(model)
    counts["seconds"] = times
    (transport_dir(name, data) / "y_exact.npy").unlink(missing_ok=True)
    write(name, data, model, result, source, counts, live["sample"])
    step("write")
    counts["seconds"] = times
    return counts
