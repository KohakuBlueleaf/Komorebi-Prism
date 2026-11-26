"""The apply's check: y against the emulation and against the set's float result, and
a command's time over the run's calls."""

import hashlib
import time

import numpy as np
from komorebi import formats

from prism.stages.indirect.transport.plan.emulate import emulate
from prism.stages.indirect.transport.plan.weights import decode_weights
from prism_common.formats import TILE

NAME = "indirect.transport"
LIT = 1e-4  # an element's luminance counted in the errors
LUMA = np.array([0.2126, 0.7152, 0.0722])


def errors(got, want, lit):
    """Per-element relative error of the luminance over the lit elements: median,
    99th percentile, most; and the ratio of the luminance sums."""
    g, w = got @ LUMA, want @ LUMA
    rel = np.abs(g[lit] - w[lit]) / w[lit]
    return {
        "median": float(np.median(rel)),
        "p99": float(np.percentile(rel, 99)),
        "most": float(rel.max()),
        "sum_ratio": float(g.sum() / w.sum()),
    }


def lit_of(host):
    """The elements counted in the errors: luminance above LIT in y_exact.npy (y_float.npy
    when the set has no y_exact.npy), not padding; and the file judged against."""
    judged = "y_exact.npy" if (host.folder / "y_exact.npy").exists() else "y_float.npy"
    lit = host.set.vector(judged) @ LUMA > LIT
    lit[np.load(host.folder / "perm.npy") < 0] = False
    return lit, judged


def y_of(session, y, tiles):
    """y's pages read while the run is loaded, as [N, 3] (rows 0 to 2 of its tiles)."""
    (raw,) = session.read(y)
    values = np.ascontiguousarray(raw).view(np.float32).reshape(tiles, TILE**2)
    return formats.untilize(values, TILE, TILE * tiles)[:3].T.copy()


def timed(loaded, host, calls):
    """`calls` applies: each command's time on the card and on the host's wall."""
    group, words = (0, host.cores), host.words("apply")
    card_us, wall_us = [], []
    for _ in range(calls):
        started = time.perf_counter()
        event = loaded.call(NAME, "apply", group, words)
        wall_us.append((time.perf_counter() - started) * 1e6)
        card_us.append(event.microseconds)
    return {
        "calls": calls,
        "card_us_median": float(np.median(card_us)),
        "card_us_least": float(np.min(card_us)),
        "wall_us_median": float(np.median(wall_us)),
        "wall_us_least": float(np.min(wall_us)),
    }


def check(loaded):
    """One apply checked against the emulation and y_float.npy, then the run's
    `calls` applies timed; the last y must equal the first."""
    host = loaded.hosts[NAME]
    s, y = host.set, host.tensors["y"]
    loaded.call(NAME, "apply", (0, host.cores), host.words("apply"))
    got = y_of(loaded.session, y, s.tiles)
    time_ = timed(loaded, host, loaded.options["calls"])
    last = y_of(loaded.session, y, s.tiles)
    emulated = emulate(s, decode_weights(host.raw), host.x)
    lit, judged = lit_of(host)
    y_float = s.vector("y_float.npy")
    return {
        "scene": host.scene,
        "sizes": host.sizes,
        "check": {
            "emulated": errors(got, emulated, lit),
            "y_float": errors(got, y_float, lit),
            "emulated_vs_y_float": errors(emulated, y_float, lit),
            "lit": int(lit.sum()),
            "lit_from": judged,
        },
        "time": time_,
        "last_equals_first": bool(np.array_equal(got, last)),
        "y_sha256": hashlib.sha256(got.tobytes()).hexdigest()[:16],
    }
