"""A binary box tree over triangles (8-word nodes): its build (median or SAH cut), its
cut into treelets, saving and loading."""

import concurrent.futures
import os
from pathlib import Path

import numpy as np

from prism_reference.scene.files import save_beside

F = np.float32
LEAF = np.uint32(0x80000000)
TREELET = np.uint32(0x40000000)
NODE_BYTES = 32
TRIANGLE_BYTES = 36
KEYS = ("nodes", "tris", "leaf_tri", "leaf_node", "meta")


def triangle_arrays(scene):
    """Vertices (N, 3, 3), v0 / e1 / e2 (N, 9) and centroids (N, 3) of the triangles."""
    p = scene["positions"][scene["indices"]]
    tris = np.concatenate([p[:, 0], p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]], axis=1)
    centroid = ((p[:, 0] + p[:, 1]) + p[:, 2]) / F(3)
    return p, tris, centroid


def sort_key(key, owner):
    """Per element a uint64 ordered as (owner, key): the owner above the float32 key's
    bits made monotonic (-0 as 0), so a stable sort of it is `np.lexsort((key, owner))`.
    """
    bits = (key.astype(np.float32) + F(0)).view(np.uint32)
    bits = np.where(bits >> 31 == 1, ~bits, bits | np.uint32(0x80000000))
    return owner.astype(np.uint64) << np.uint64(32) | bits


def segment_order(key, owner, first):
    """`np.lexsort((key, owner))` of segments starting at `first` (owner ascending),
    sorted as runs of whole segments on the process's CPUs."""
    runs = min(len(os.sched_getaffinity(0)), len(first))
    cuts = np.searchsorted(first, np.linspace(0, len(key), runs + 1)[1:-1])
    inner = first[np.minimum(cuts, len(first) - 1)]
    edges = np.unique(np.concatenate([[0], inner, [len(key)]]))

    def run(a, b):
        return np.argsort(sort_key(key[a:b], owner[a:b]), kind="stable") + a

    with concurrent.futures.ThreadPoolExecutor(len(edges) - 1) as pool:
        return np.concatenate(list(pool.map(run, edges[:-1], edges[1:])))


def split_levels(centroid):
    """Levels of (first node, handler starts, counts) and the final triangle order."""
    n = len(centroid)
    perm = np.arange(n)
    start, count, base = np.array([0]), np.array([n]), 0
    levels = []
    while len(start):
        levels.append((base, start, count))
        first = np.cumsum(count) - count
        owner = np.repeat(np.arange(len(start)), count)
        pos = np.repeat(start - first, count) + np.arange(int(count.sum()))
        c = centroid[perm[pos]]
        lo = np.minimum.reduceat(c, first, axis=0)
        hi = np.maximum.reduceat(c, first, axis=0)
        axis = np.argmax(hi - lo, axis=1)
        key = c[np.arange(len(pos)), axis[owner]]
        perm[pos] = perm[pos][segment_order(key, owner, first)]
        inner = count > 1
        left = (count[inner] + 1) // 2
        start = np.stack([start[inner], start[inner] + left], axis=1).ravel()
        count = np.stack([left, count[inner] - left], axis=1).ravel()
        base += len(inner)
    return levels, perm


def presorted_levels(centroid):
    """As `split_levels` (median cut on the longest axis), each axis sorted once and
    the sorted orders split stably by the cut: O(n) a level; equal keys keep the
    first sort's order."""
    n = len(centroid)
    orders = np.stack([np.argsort(centroid[:, a], kind="stable") for a in range(3)])
    flag = np.zeros(n, dtype=bool)
    start, count, base = np.array([0]), np.array([n]), 0
    levels = []
    while len(start):
        levels.append((base, start, count))
        last = start + count - 1
        extent = np.stack(
            [
                centroid[orders[a, last], a] - centroid[orders[a, start], a]
                for a in range(3)
            ],
            axis=1,
        )
        axis = np.argmax(extent, axis=1)
        left = (count + 1) // 2
        first = np.cumsum(count) - count
        owner = np.repeat(np.arange(len(start)), count)
        rank = np.arange(int(count.sum())) - first[owner]
        pos = start[owner] + rank
        flag[orders[axis[owner], pos]] = rank >= left[owner]
        for a in range(3):
            t = orders[a, pos]
            f = flag[t]
            before = np.cumsum(f) - f
            before = before - before[first][owner]
            place = np.where(f, left[owner] + before, rank - before)
            orders[a, start[owner] + place] = t
        inner = count > 1
        left = left[inner]
        start = np.stack([start[inner], start[inner] + left], axis=1).ravel()
        count = np.stack([left, count[inner] - left], axis=1).ravel()
        base += len(inner)
    return levels, orders[0]


SAH_BINS = 16
SAH_LEVELS = 40  # from this level on every cut is the median cut
SAH_MAX_LEVELS = 60


def sah_levels(p, centroid):
    """As `split_levels`, each segment cut by the surface-area heuristic over 16 bins
    per axis (no plane: half by the current order); from SAH_LEVELS on, the median."""
    n = len(centroid)
    tri_lo, tri_hi = p.min(axis=1), p.max(axis=1)
    perm = np.arange(n)
    start, count, base = np.array([0]), np.array([n]), 0
    levels = []
    while len(start):
        levels.append((base, start, count))
        segments = len(start)
        first = np.cumsum(count) - count
        owner = np.repeat(np.arange(segments), count)
        pos = np.repeat(start - first, count) + np.arange(int(count.sum()))
        c = centroid[perm[pos]]
        lo = np.minimum.reduceat(c, first, axis=0)
        hi = np.maximum.reduceat(c, first, axis=0)
        if len(levels) - 1 >= SAH_LEVELS:
            axis = np.argmax(hi - lo, axis=1)
            key = c[np.arange(len(pos)), axis[owner]]
            left = (count + 1) // 2
        else:
            key, left = sah_cut(
                c, tri_lo[perm[pos]], tri_hi[perm[pos]], lo, hi, owner, count
            )
        perm[pos] = perm[pos][np.lexsort((key, owner))]
        inner = count > 1
        left = left[inner]
        start = np.stack([start[inner], start[inner] + left], axis=1).ravel()
        count = np.stack([left, count[inner] - left], axis=1).ravel()
        base += segments
    return levels, perm


def box_area(lo, hi):
    """2 (dx dy + dy dz + dz dx) of boxes (..., 3), float64."""
    d = hi.astype(np.float64) - lo
    return 2 * (d[..., 0] * d[..., 1] + d[..., 1] * d[..., 2] + d[..., 2] * d[..., 0])


def sah_cut(c, b_lo, b_hi, lo, hi, owner, count):
    """Sort key (0 left, 1 right; all 0 where no plane) of each triangle of a level and
    the left count of each segment."""
    segments, bins = len(count), SAH_BINS
    best_cost = np.full(segments, np.inf)
    best_axis = np.zeros(segments, dtype=np.int64)
    best_plane = np.zeros(segments, dtype=np.int64)
    best_left = np.zeros(segments, dtype=np.int64)
    bin_of = []
    for a in range(3):
        extent = (hi[:, a].astype(np.float64) - lo[:, a])[owner]
        rel = c[:, a].astype(np.float64) - lo[owner, a]
        safe = np.where(extent > 0, extent, 1.0)
        b = np.clip((rel * bins / safe).astype(np.int64), 0, bins - 1)
        b[extent <= 0] = 0
        bin_of.append(b)
        key = owner * bins + b
        order = np.argsort(key, kind="stable")
        sorted_key = key[order]
        heads = np.flatnonzero(np.r_[True, sorted_key[1:] != sorted_key[:-1]])
        group = sorted_key[heads]
        g_lo = np.full((segments * bins, 3), np.inf, dtype=np.float32)
        g_hi = np.full((segments * bins, 3), -np.inf, dtype=np.float32)
        g_lo[group] = np.minimum.reduceat(b_lo[order], heads, axis=0)
        g_hi[group] = np.maximum.reduceat(b_hi[order], heads, axis=0)
        g_lo, g_hi = g_lo.reshape(segments, bins, 3), g_hi.reshape(segments, bins, 3)
        n_bin = np.bincount(key, minlength=segments * bins).reshape(segments, bins)
        n_left = np.cumsum(n_bin, axis=1)[:, :-1]
        n_right = count[:, None] - n_left
        l_lo = np.minimum.accumulate(g_lo, axis=1)[:, :-1]
        l_hi = np.maximum.accumulate(g_hi, axis=1)[:, :-1]
        r_lo = np.minimum.accumulate(g_lo[:, ::-1], axis=1)[:, ::-1][:, 1:]
        r_hi = np.maximum.accumulate(g_hi[:, ::-1], axis=1)[:, ::-1][:, 1:]
        valid = (n_left > 0) & (n_right > 0)
        with np.errstate(invalid="ignore"):
            cost = n_left * box_area(l_lo, l_hi) + n_right * box_area(r_lo, r_hi)
        cost = np.where(valid, cost, np.inf)
        plane = np.argmin(cost, axis=1)
        least = cost[np.arange(segments), plane]
        better = least < best_cost
        best_cost[better], best_axis[better] = least[better], a
        best_plane[better] = plane[better]
        best_left[better] = n_left[np.arange(segments), plane][better]
    found = np.isfinite(best_cost)
    b = np.choose(best_axis[owner], bin_of)
    key = np.where(found[owner], b > best_plane[owner], False).astype(np.int64)
    left = np.where(found, best_left, (count + 1) // 2)
    return key, left


def build(scene, split="median"):
    """The tree of a scene as a dict of the arrays named in KEYS; split "median" (the
    median cut on the longest axis), "presorted" (the same cut, `presorted_levels`)
    or "sah" (`sah_levels`)."""
    p, tris, centroid = triangle_arrays(scene)
    if split == "median":
        levels, perm = split_levels(centroid)
    elif split == "presorted":
        levels, perm = presorted_levels(centroid)
    elif split == "sah":
        levels, perm = sah_levels(p, centroid)
    else:
        raise ValueError(f"unknown split {split!r}")
    node_count = 2 * len(perm) - 1
    box = np.empty((node_count, 6), dtype=np.float32)
    nodes = np.empty((node_count, 8), dtype=np.uint32)
    leaf_node = np.empty(len(perm), dtype=np.int32)
    first_child = []
    for base, start, count in levels:
        ids = base + np.arange(len(start))
        leaf = count == 1
        t = perm[start[leaf]]
        box[ids[leaf], :3] = p[t].min(axis=1)
        box[ids[leaf], 3:] = p[t].max(axis=1)
        word = LEAF | start[leaf].astype(np.uint32)
        nodes[ids[leaf], 6] = nodes[ids[leaf], 7] = word
        leaf_node[start[leaf]] = ids[leaf]
        next_base = base + len(start)
        first_child.append(next_base + 2 * np.arange(int((~leaf).sum())))
        nodes[ids[~leaf], 6] = first_child[-1]
        nodes[ids[~leaf], 7] = first_child[-1] + 1
    for (base, start, count), child in zip(levels[::-1], first_child[::-1]):
        ids = (base + np.arange(len(start)))[count > 1]
        box[ids, :3] = np.minimum(box[child, :3], box[child + 1, :3])
        box[ids, 3:] = np.maximum(box[child, 3:], box[child + 1, 3:])
    nodes[:, :6] = box.view(np.uint32)
    meta = np.array([node_count, len(perm), len(levels) - 1], dtype=np.int32)
    if split == "sah":
        assert meta[2] <= SAH_MAX_LEVELS, f"sah tree of {meta[2]} levels"
    return {
        "nodes": nodes,
        "tris": tris[perm],
        "leaf_tri": perm.astype(np.int32),
        "leaf_node": leaf_node,
        "meta": meta,
    }


def node_boxes(nodes):
    """Box min and max (N, 3) float32 of nodes (N, 8) uint32."""
    box = np.ascontiguousarray(nodes[:, :6]).view(np.float32)
    return box[:, :3], box[:, 3:]


def is_leaf(words):
    """True where a child word marks a leaf."""
    return (words & LEAF) != 0


def levels_of(tree):
    """Node ids by level (breadth first numbering makes each level a range)."""
    nodes, ids, out = tree["nodes"], np.array([0]), []
    while len(ids):
        out.append(ids)
        inner = ids[~is_leaf(nodes[ids, 6])]
        ids = np.stack([nodes[inner, 6], nodes[inner, 7]], axis=1).ravel()
    return out


def cut_treelets(tree, max_bytes):
    """Cuts the tree into treelets of at most max_bytes and a top tree over them (a
    top child word: a top node, or 0x40000000 | treelet); a dict of their arrays."""
    nodes, node_count = tree["nodes"], len(tree["nodes"])
    levels = levels_of(tree)
    size = np.zeros(node_count, dtype=np.int64)
    leaves = np.zeros(node_count, dtype=np.int64)
    for ids in levels[::-1]:
        leaf = is_leaf(nodes[ids, 6])
        size[ids[leaf]], leaves[ids[leaf]] = NODE_BYTES + TRIANGLE_BYTES, 1
        inner = ids[~leaf]
        c0, c1 = nodes[inner, 6], nodes[inner, 7]
        size[inner] = NODE_BYTES + size[c0] + size[c1]
        leaves[inner] = leaves[c0] + leaves[c1]
    top = size > max_bytes
    node_treelet = np.full(node_count, -1, dtype=np.int32)
    roots = [0] if not top[0] else []
    for ids in levels:
        inner = ids[~is_leaf(nodes[ids, 6])]
        for c in (nodes[inner, 6], nodes[inner, 7]):
            roots += c[top[inner] & ~top[c]].tolist()
    roots = np.array(sorted(roots), dtype=np.int32)
    node_treelet[roots] = np.arange(len(roots))
    for ids in levels:
        inner = ids[~is_leaf(nodes[ids, 6])]
        inner = inner[node_treelet[inner] >= 0]
        node_treelet[nodes[inner, 6]] = node_treelet[inner]
        node_treelet[nodes[inner, 7]] = node_treelet[inner]
    k = len(roots)
    members = np.nonzero(node_treelet >= 0)[0]
    members = members[np.argsort(node_treelet[members], kind="stable")]
    node_off = np.concatenate(
        [[0], np.cumsum(np.bincount(node_treelet[members], minlength=k))]
    )
    local = np.full(node_count, -1, dtype=np.int64)
    local[members] = np.arange(len(members)) - node_off[node_treelet[members]]
    leaf_first = np.array(
        [nodes[leaf_range_node(nodes, r)[0], 6] & ~LEAF for r in roots], dtype=np.int64
    )
    tl_nodes = nodes[members].copy()
    inner = ~is_leaf(tl_nodes[:, 6])
    tl_nodes[inner, 6] = local[tl_nodes[inner, 6]]
    tl_nodes[inner, 7] = local[tl_nodes[inner, 7]]
    word = tl_nodes[~inner, 6] & ~LEAF
    owner = node_treelet[members][~inner]
    tl_nodes[~inner, 6] = tl_nodes[~inner, 7] = LEAF | (
        word - leaf_first[owner]
    ).astype(np.uint32)
    leaf_off = np.concatenate([[0], np.cumsum(leaves[roots])])
    tl_tris = np.concatenate(
        [tree["tris"][a : a + n] for a, n in zip(leaf_first, leaves[roots])]
    )
    top_ids = np.nonzero(node_treelet < 0)[0]
    top_local = np.full(node_count, -1, dtype=np.int64)
    top_local[top_ids] = np.arange(len(top_ids))
    top_nodes = nodes[top_ids].copy()
    for col in (6, 7):
        child = top_nodes[:, col].astype(np.int64)
        to_top = node_treelet[child] < 0
        top_nodes[:, col] = np.where(
            to_top, top_local[child], TREELET | node_treelet[child]
        )
    top_root = np.array([0 if len(top_ids) else TREELET], dtype=np.uint32)
    return {
        "treelet_root": roots,
        "node_treelet": node_treelet,
        "treelet_node_off": node_off.astype(np.int32),
        "treelet_leaf_first": leaf_first.astype(np.int32),
        "treelet_leaf_off": leaf_off.astype(np.int32),
        "treelet_nodes": tl_nodes,
        "treelet_tris": tl_tris,
        "top_nodes": top_nodes,
        "top_root": top_root,
    }


def leaf_range_node(nodes, root):
    """The leftmost leaf node under `root` (its child word names the first leaf)."""
    node = int(root)
    while not is_leaf(nodes[node, 6]):
        node = int(nodes[node, 6])
    return node, node


def save_tree(path, tree):
    """Saves a tree as an uncompressed .npz (save_beside)."""
    save_beside(path, lambda name: np.savez(name, **tree))


def load_tree(path):
    """Loads a tree saved by `save_tree`."""
    with np.load(path) as data:
        return {key: data[key] for key in KEYS}


def export_npy(tree, folder):
    """Writes each array of a tree as <folder>/<key>.npy, the input of the C++ code."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for key in KEYS:
        save_beside(folder / f"{key}.npy", lambda name, k=key: np.save(name, tree[k]))
