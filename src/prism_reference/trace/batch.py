"""Many rays at once over a box tree, by the compiled batch routine, threaded."""

import os

import numpy as np

from prism_reference.native.loader import library

F = np.float32
THREADS_VARIABLE = "PRISM_THREADS"


def threads():
    """Threads of the batch ray routine: $PRISM_THREADS, else the CPUs this process may
    use, at most 8."""
    if THREADS_VARIABLE in os.environ:
        return int(os.environ[THREADS_VARIABLE])
    return max(1, min(8, len(os.sched_getaffinity(0))))


def trace(tree, origin, direction, tmax, any_hit=False):
    """t, triangle (-1: none), u, v (n,) of rays origin + t direction with t < tmax (a
    number or (n,)); the reference tree walk and triangle test, threaded."""
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
    library().trace_batch(
        *(tree[k].ctypes.data for k in ("nodes", "tris", "leaf_tri")),
        o.ctypes.data,
        d.ctypes.data,
        tm.ctypes.data,
        n,
        int(any_hit),
        *(a.ctypes.data for a in (t, leaf, u, v)),
        threads(),
    )
    tri = np.where(leaf >= 0, tree["leaf_tri"][np.maximum(leaf, 0)], -1)
    return t, tri, u, v
