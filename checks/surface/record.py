"""The results of the check's cases."""

import numpy as np

RESULTS = []


def same(case, got, want, tolerance=1e-6):
    """Records whether `got` equals `want` within `tolerance` (exact for booleans and
    integers)."""
    g, w = np.asarray(got), np.asarray(want)
    if g.shape != w.shape:
        equal = False
    elif g.dtype.kind in "biu" and w.dtype.kind in "biu":
        equal = bool(np.array_equal(g, w))
    else:
        equal = bool(np.all(np.abs(g.astype(np.float64) - w) <= tolerance))
    RESULTS.append({"case": case, "equal": equal})
    if not equal:
        RESULTS[-1]["got"], RESULTS[-1]["want"] = repr(got)[:200], repr(want)[:200]
    return equal


def at_most(case, got, bound):
    """Records whether every value of `got` is at most `bound`."""
    equal = bool(np.all(np.asarray(got) <= bound))
    RESULTS.append({"case": case, "equal": equal})
    if not equal:
        RESULTS[-1]["got"], RESULTS[-1]["want"] = repr(got)[:200], f"<= {bound}"
    return equal
