"""The check's record: every comparison and refusal, with its outcome."""

import numpy as np

RESULTS = []
TOLERANCE = 1e-6


def same(case, got, want):
    """Records whether `got` equals `want`: exact for integers and text, 1e-6 for floats."""
    try:
        if got is None or want is None or isinstance(want, str | bool):
            equal = got == want
        else:
            g, w = np.asarray(got), np.asarray(want)
            if g.shape != w.shape:
                equal = False
            elif g.dtype.kind == "f" or w.dtype.kind == "f":
                equal = bool(np.allclose(g, w, rtol=0, atol=TOLERANCE))
            else:
                equal = bool(np.array_equal(g, w))
    except (TypeError, ValueError):
        equal = False
    RESULTS.append({"case": case, "equal": bool(equal)})
    if not equal:
        RESULTS[-1]["got"], RESULTS[-1]["want"] = repr(got)[:200], repr(want)[:200]
    return equal


def refused(case, call, words):
    """Records whether `call()` raises ValueError with `words` in its message."""
    try:
        call()
        message = None
    except ValueError as error:
        message = str(error)
    equal = message is not None and words in message
    RESULTS.append({"case": f"refusal: {case}", "equal": equal})
    if not equal:
        RESULTS[-1]["got"] = message
    return equal
