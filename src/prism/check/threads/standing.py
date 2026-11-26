"""Where a frame of the threads' form stood when it ended badly (a code, a wait that
ran out, a hang): the X280 thread's last progress mark, the view's times and results,
and each core's gave-up words, every code decoded by name. Printed and returned."""

import sys

import komorebi as km
import numpy as np

from prism.check.threads import codes, names
from prism.core.resources import TIMES_ROWS
from prism.program.loaded import MICROSECONDS

THREAD_WAIT_S = 2.0  # seconds the thread's result is waited for before its stop
KERNELS = ("reader", "writer", "compute")


def say(line):
    """A line of the standing, to stderr."""
    print(f"  standing: {line}", file=sys.stderr, flush=True)


def row_at(loaded, number):
    """The times row of frame `number` (from 0; the one in flight may be partial):
    {name: value} of the dispatcher's times (us) and results."""
    layout = loaded.layout
    words = layout.times_words
    raw = np.frombuffer(loaded.thread.read("times"), dtype=np.uint32)
    row = raw[: TIMES_ROWS * words].reshape(TIMES_ROWS, words)[number % TIMES_ROWS]
    out = {}
    for name, place, where in loaded.places(layout.times):
        if name in names.TIMES or name == "frame":
            out[name] = loaded.by_layer(
                place, [float(row[w]) * MICROSECONDS for w in where]
            )
    for name, place, where in loaded.places(layout.results):
        if name in names.RESULTS or name == "code":
            out[name] = loaded.by_layer(place, [int(row[w]) for w in where])
    return out


def thread_marks(loaded):
    """{cluster: (ran, state, last progress mark by name, code by name)} of the X280
    threads, waited for THREAD_WAIT_S and stopped."""
    try:
        results = loaded.run.thread_results(timeout=THREAD_WAIT_S)
    except km.KomorebiError as error:
        results = getattr(error, "results", None) or {}
        say(f"the threads' results: {error}")
    return {
        cluster: {
            "ran": bool(result.ran),
            "state": result.state,
            "error": result.error,
            "where": codes.progress_name(result.where),
            "code": codes.result_name(result.code),
            "stuck": bool(result.stuck),
        }
        for cluster, result in results.items()
    }


def gave_ups(state):
    """Each core's gave-up words that are set: [{core, kernel, code, where by name,
    slot, sequence}] of Run.state()'s dicts."""
    out = []
    for core in state:
        for kernel in KERNELS:
            gave = core.get(kernel)
            if not gave:
                continue
            out.append(
                {
                    "core": int(core["core"]),
                    "kernel": kernel,
                    "code": gave["code"],
                    "where": codes.where_name(gave["where"]),
                    "slot": gave.get("slot"),
                    "sequence": gave.get("sequence"),
                }
            )
    return out


def standing(loaded, code=None, error=None):
    """Where the frame stood: the thread's marks, the run stopped, the cores' gave-up
    words, the view's row in flight and the rows served; each printed."""
    out = {"code": None if code is None else codes.result_name(code)}
    out["error"] = None if error is None else str(error)
    say(f"code {out['code']}, error {out['error']}")
    out["threads"] = thread_marks(loaded)
    for cluster, marks in out["threads"].items():
        say(f"X280 cluster {cluster}: {marks}")
    try:
        loaded.stop()
    except km.KomorebiError as stopped:
        out["stop"] = str(stopped)
        say(f"the stop: {stopped}")
    try:
        state = loaded.run.state()
    except km.KomorebiError as unread:
        state = []
        out["state"] = str(unread)
        say(f"the cores' state: {unread}")
    out["gave_up"] = gave_ups(state)
    out["cores_read"] = len(state)
    out["cores_gave_up"] = len({one["core"] for one in out["gave_up"]})
    say(f"{out['cores_gave_up']} of {len(state)} cores gave up")
    for one in out["gave_up"][:32]:
        say(
            f"core {one['core']} {one['kernel']}: {one['code']} at {one['where']} "
            f"(slot {one['slot']}, command {one['sequence']})"
        )
    if loaded.layout is not None:
        out["row_in_flight"] = row_at(loaded, loaded.served)
        say(f"the view's row in flight: {out['row_in_flight']}")
        out["rows"] = loaded.times()
    return out
