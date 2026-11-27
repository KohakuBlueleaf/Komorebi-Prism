"""A map over bands of a frame by forked processes that inherit the band's inputs."""

import multiprocessing
import signal

_SHARED = {}  # the map's function and inputs, inherited by the fork


def _one(item):
    """The held function on one item."""
    fn, inputs = _SHARED["job"]
    return fn(*inputs, item)


def _plain():
    """A worker's signals as the default: the parent's handlers are not run in it."""
    for one in (signal.SIGTERM, signal.SIGINT):
        signal.signal(one, signal.SIG_DFL)


def forked_map(fn, inputs, items, workers):
    """[fn(*inputs, item) for item in items], by `workers` forked processes when > 1,
    closed and joined (never terminated)."""
    if workers <= 1:
        return [fn(*inputs, item) for item in items]
    _SHARED["job"] = (fn, inputs)
    pool = multiprocessing.get_context("fork").Pool(workers, initializer=_plain)
    try:
        out = pool.map(_one, items)
        pool.close()
        pool.join()
        return out
    finally:
        pool.terminate()
        _SHARED.clear()
