"""A map over bands of a frame by forked processes that inherit the band's inputs."""

import multiprocessing

_SHARED = {}  # the map's function and inputs, inherited by the fork


def _one(item):
    """The held function on one item."""
    fn, inputs = _SHARED["job"]
    return fn(*inputs, item)


def forked_map(fn, inputs, items, workers):
    """[fn(*inputs, item) for item in items], by `workers` forked processes when > 1."""
    if workers <= 1:
        return [fn(*inputs, item) for item in items]
    _SHARED["job"] = (fn, inputs)
    try:
        with multiprocessing.get_context("fork").Pool(workers) as pool:
            return pool.map(_one, items)
    finally:
        _SHARED.clear()
