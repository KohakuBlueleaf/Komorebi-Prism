"""Builds a scene's transport over a few thousand elements densely and block by block
and compares them (no card); one JSON line with `ok`, exit 1 on a difference."""

import argparse
import json
import sys
import time

import numpy as np

from prism_common.paths import data_root
from prism_reference.indirect.blockwise.build import far_rows, ray_tree
from prism_reference.indirect.blockwise.near import near_blocks
from prism_reference.indirect.elements import padded, sample_elements, subset
from prism_reference.indirect.form_factors import form_factor_rows
from prism_reference.indirect.hmatrix.apply import apply
from prism_reference.indirect.hmatrix.cluster import UNIT, cluster_tree, partition
from prism_reference.indirect.hmatrix.compress import TOLERANCE, hierarchical, pack
from prism_reference.scene.public.materials import load_materials
from prism_reference.scene.public.mesh import load_mesh
from prism_reference.scene.public.views import EPS_SCALE
from prism_reference.trace.batch import trace
from prism_reference.trace.tree import build

# The block-by-block error may pass the dense build's (its SVD's truncation) by this
# share: the randomized range finds the same singular values up to rounding.
SLACK = 0.1
RAYS, RAY_SEED = 200_000, 81  # random segments the two median trees trace


def stored(blocks, weights, count):
    """The dense matrix (count, count) float64 of stored blocks."""
    out = np.zeros((count, count))
    keys = ("row0", "row1", "col0", "col1", "kind", "rank_padded", "offset_a")
    for r0, r1, c0, c1, kd, kp, oa, ob in zip(
        *(blocks[k] for k in keys + ("offset_b",))
    ):
        m, n = r1 - r0, c1 - c0
        if kd == 0:
            out[r0:r1, c0:c1] = weights[oa : oa + n * m].reshape(n, m).T
        else:
            v = weights[oa : oa + n * kp].reshape(n, kp)
            out[r0:r1, c0:c1] = (v @ weights[ob : ob + kp * m].reshape(kp, m)).T
    return out


def main():
    """Dense and block-by-block blocks of the same elements: y = M x and the admissible
    blocks' error against the dense matrix; the presorted and median trees' hits."""
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("--scene", default="sponza")
    parser.add_argument("--elements", type=int, default=6000)
    args = parser.parse_args()
    started = time.perf_counter()
    data = data_root()
    mesh, _ = load_mesh(args.scene, data)
    materials, _ = load_materials(args.scene, data)
    tree = ray_tree(mesh, materials)
    p = mesh["positions"].astype(np.float64)
    eps = EPS_SCALE * float(np.linalg.norm(p.max(0) - p.min(0)))
    sampled, _ = sample_elements(mesh, materials, args.elements)
    count = -(-args.elements // UNIT) * UNIT
    elements, real = padded(sampled, count)
    cluster = cluster_tree(elements["position"])
    elements, real = subset(elements, cluster["perm"]), real[cluster["perm"]]
    dense, _ = form_factor_rows(tree, elements, np.arange(count), eps)
    dense[~real], dense[:, ~real] = 0, 0
    matrix = dense * np.float32(np.pi)
    admissible, near = partition(cluster)
    start, end = cluster["start"], cluster["end"]
    found, _ = near_blocks(tree, elements, real, eps, cluster, near, True)
    rows = [
        (start[a], end[a], start[b], end[b], 0, 0, block.T.copy(), None)
        for (a, b), block in zip(near, found)
        if block.any()
    ]
    count_near = len(rows)
    far, _, _ = far_rows(
        tree, elements, real, eps, cluster, admissible, True, "sketch", TOLERANCE, print
    )
    rows += [
        (start[a], end[a], start[b], end[b], *row)
        for (a, b), row in zip(admissible, far)
        if row is not None
    ]
    built = {"sketch": pack(rows, count_near), "svd": hierarchical(matrix, cluster)}
    x = np.random.default_rng(0).random((count, 3)).astype(np.float32) * real[:, None]
    exact = matrix.astype(np.float64) @ x
    far_mask = np.zeros((count, count), dtype=bool)
    for a, b in admissible:
        far_mask[start[a] : end[a], start[b] : end[b]] = True
    report = {}
    for name, (blocks, weights) in built.items():
        y = apply(blocks, weights, x)
        whole = stored(blocks, weights, count)
        report[name] = {
            "y": float(np.linalg.norm(y - exact) / np.linalg.norm(exact)),
            "far": float(
                np.linalg.norm((whole - matrix)[far_mask])
                / np.linalg.norm(matrix[far_mask])
            ),
            "near": float(
                np.linalg.norm((whole - matrix)[~far_mask])
                / np.linalg.norm(matrix[~far_mask])
            ),
        }
    rng = np.random.default_rng(RAY_SEED)
    lo, hi = p.min(0), p.max(0)
    origin = (lo + rng.random((RAYS, 3)) * (hi - lo)).astype(np.float32)
    direction = ((lo + rng.random((RAYS, 3)) * (hi - lo)) - origin).astype(np.float32)
    hits = []
    for split in ("median", "presorted"):
        other = {k: np.ascontiguousarray(v) for k, v in build(mesh, split).items()}
        hits.append(trace(other, origin, direction, 1.0, any_hit=True)[1] >= 0)
    s, d = report["sketch"], report["svd"]
    ok = (
        s["y"] <= (1 + SLACK) * d["y"] + 1e-7
        and s["far"] <= (1 + SLACK) * d["far"] + 1e-7
        and bool(np.array_equal(hits[0], hits[1]))
    )
    line = {"ok": bool(ok), "elements": count, "errors": report}
    line["tree_hits_differ"] = int((hits[0] != hits[1]).sum())
    line["seconds"] = round(time.perf_counter() - started, 1)
    print(json.dumps(line))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
