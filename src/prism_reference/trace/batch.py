"""Many rays at once over a box tree, by the compiled batch routine over the host's own
tree of the box tree's triangles (made once a tree), threaded."""

import os
import threading
import weakref

import numpy as np

from prism_reference.native.loader import library

F = np.float32
THREADS_VARIABLE = "PRISM_THREADS"
LEAF_MOST = 4  # triangles a leaf of the host's tree holds at most
HOST_TREES = {}  # id of a tree's triangles -> (a weak reference to them, the tree)
MAKING = threading.RLock()  # a finalizer may run inside the making


def threads():
    """Threads of the batch ray routine: $PRISM_THREADS, else the CPUs this process may
    use, at most 8."""
    if THREADS_VARIABLE in os.environ:
        return int(os.environ[THREADS_VARIABLE])
    return max(1, min(8, len(os.sched_getaffinity(0))))


def host_tree(tree):
    """The host's tree of `tree`'s triangles (surface-area cuts, leaves of at most
    LEAF_MOST), made on first use and freed with the triangles' array."""
    tris = tree["tris"]
    with MAKING:
        kept = HOST_TREES.get(id(tris))
        if kept is not None and kept[0]() is tris:
            return kept[1]
        lib = library()
        scene = np.ascontiguousarray(tree["leaf_tri"], np.int32)
        made = lib.host_tree_make(
            np.ascontiguousarray(tris, F).ctypes.data,
            scene.ctypes.data,
            len(tris),
            LEAF_MOST,
            0,
            max(threads(), len(os.sched_getaffinity(0))),
        )
        HOST_TREES[id(tris)] = (weakref.ref(tris), made)
        weakref.finalize(tris, forget, id(tris), made)
        return made


def forget(key, made):
    """The host's tree `made` freed and dropped from HOST_TREES."""
    with MAKING:
        if key in HOST_TREES and HOST_TREES[key][1] == made:
            del HOST_TREES[key]
    library().host_tree_free(made)


def trace(tree, origin, direction, tmax, any_hit=False, count=None):
    """t, triangle (-1: none), u, v (n,) of rays origin + t direction with t < tmax (a
    number or (n,)); the reference triangle test over the host's tree, the rays in the
    order of their origins' cells, on `count` threads (`threads()` when None)."""
    o = np.ascontiguousarray(origin, F)
    d = np.ascontiguousarray(direction, F)
    n = len(o)
    tm = np.ascontiguousarray(np.broadcast_to(np.asarray(tmax, F), (n,)), F)
    t, leaf, u, v = (
        np.empty(n, F),
        np.empty(n, np.int32),
        np.empty(n, F),
        np.empty(n, F),
    )
    library().host_trace_batch(
        host_tree(tree),
        o.ctypes.data,
        d.ctypes.data,
        tm.ctypes.data,
        n,
        int(any_hit),
        *(a.ctypes.data for a in (t, leaf, u, v)),
        threads() if count is None else int(count),
    )
    tri = np.where(leaf >= 0, tree["leaf_tri"][np.maximum(leaf, 0)], -1)
    return t, tri, u, v
