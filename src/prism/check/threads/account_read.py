"""The account's pages read after a frame (frame/kernels/frame.h FX_*): each core's
blocks by (view, pull), its records of the frame's threads, the X280 choice's words by
core; summed into bytes by path, a core's time, the CPUs by step."""

import numpy as np

from prism.check.threads import names
from prism.check.threads.card import read_words
from prism.check.threads.model import PORTS_CORES
from prism.program.dispatch.thread import CHOOSE
from prism.program.frame.generate import FRAME

PULLS = ("count", "place", "tile")
MOVER = {"a": FRAME["FX_MOVER_A"], "b": FRAME["FX_MOVER_B"]}
TIMES = ("ask", "none", "ahead", "drain", "span", "run", "serve")
BYTES = ("mesh", "shade", "lists", "records", "asked", "out", "pages", "other")
CPUS = ("unpack", "math", "pack")
CHOICE = ("answers", "nones", "ticks")  # dp_core_t words 4, 5, 6


def pages(loop):
    """The account's pages [cores, words] as they stand; None without the account."""
    tensor = getattr(loop.threaded.frame, "account_pages", None)
    if tensor is None:
        return None
    return read_words(loop.session, tensor)


def blocks(words):
    """[cores, views, pulls, block words] of `words`."""
    at, size = FRAME["FX_PAGE_BLOCKS"], FRAME["FX_BLOCK_WORDS"]
    count = FRAME["FX_VIEWS"] * FRAME["FX_ACCOUNT_PULLS"]
    out = words[:, at : at + count * size]
    return out.reshape(len(words), FRAME["FX_VIEWS"], FRAME["FX_ACCOUNT_PULLS"], size)


def records(words, before):
    """The records written since `before` (head word 0 of each core's page as it was):
    [n, 1 + record words] with the core first; the counts now."""
    held = (words.shape[1] - FRAME["FX_RECORDS_AT"]) // FRAME["FX_RECORD_WORDS"]
    ring = words[:, FRAME["FX_RECORDS_AT"] :].reshape(len(words), held, -1)
    now = words[:, 0].astype(np.int64)
    rows, lost = [], 0
    for core in range(len(words)):
        first = max(int(before[core]), int(now[core]) - held)
        lost += first - int(before[core])
        for index in range(first, int(now[core])):
            rows.append(np.concatenate(([core], ring[core, index % held])))
    width = 1 + FRAME["FX_RECORD_WORDS"]
    out = np.array(rows, dtype=np.int64).reshape(-1, width)
    return out, now, lost


def choice(loop):
    """[cores, answers / nones / ticks] of the last tile pull's choice (read after the
    stop)."""
    raw = np.frombuffer(loop.loaded.region(names.STATE), dtype=np.uint32)
    head, size = CHOOSE["DP_CHOOSE_HEAD_WORDS"], CHOOSE["DP_CORE_WORDS"]
    cores = raw[head : head + size * PORTS_CORES].reshape(-1, size)
    first, count = int(raw[3]), int(raw[4])
    return cores[first : first + count, 4:7].astype(np.int64)


def spread(values, mhz=None):
    """[median, min, max, mean] of `values` (ms from cycles when `mhz`)."""
    values = np.asarray(values, dtype=np.float64)
    if mhz:
        values = values / (mhz * 1e3)
    if not values.size:
        return None
    return [
        round(float(np.median(values)), 4),
        round(float(values.min()), 4),
        round(float(values.max()), 4),
        round(float(values.mean()), 4),
    ]


def summary(block, views, mhz):
    """The frame's account from `block` [cores, views, pulls, words] over the `views`
    used: bytes by path (summed over cores), each mover's and CPU's times (spread over
    the cores, ms), the CPUs' steps."""
    used = block[:, list(views)].astype(np.int64)
    out = {"bytes": {}, "time": {}, "threads": {}, "cpu": {}}
    for index, path in enumerate(BYTES):
        word = FRAME["FX_BYTES_MESH"] + index
        both = used[..., MOVER["a"] + word] + used[..., MOVER["b"] + word]
        out["bytes"][path] = int(both.sum())
        for p, pull in enumerate(PULLS):
            out["bytes"][f"{pull}.{path}"] = int(both[:, :, p].sum())
    place = used[:, :, PULLS.index("place")].sum(axis=1)
    for name in ("FX_PLACE_LOAD", "FX_PLACE_WAIT"):
        out["time"][name.lower()[3:]] = spread(place[:, FRAME[name]], mhz)
    for p, pull in enumerate(PULLS):
        one = used[:, :, p]
        out["threads"][pull] = spread(one[..., FRAME["FX_THREADS"]].sum(axis=1))
        for mover, base in MOVER.items():
            for index, name in enumerate(TIMES):
                word = base + FRAME["FX_ASK"] + index
                key = f"{pull}.{mover}.{name}"
                out["time"][key] = spread(one[..., word].sum(axis=1), mhz)
        for c, cpu in enumerate(CPUS):
            base = FRAME["FX_CPU_AT"] + c * FRAME["FX_CPU_WORDS"]
            out["cpu"][f"{pull}.{cpu}.threads"] = spread(
                one[..., base].sum(axis=1), mhz
            )
            steps = one[
                ..., base + FRAME["FX_CPU_STEP"] : base + FRAME["FX_CPU_THREADS"]
            ]
            out["cpu"][f"{pull}.{cpu}.steps"] = [
                spread(steps[..., s].sum(axis=1), mhz) for s in range(steps.shape[-1])
            ]
    return out
