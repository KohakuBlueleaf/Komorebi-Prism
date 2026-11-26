"""The account of the threads' form: frames of the stage-wise preset and of its threads'
preset at each way of handing out, each frame's picture judged against the stage-wise
one, the frame's and each phase's time from the times rows read after the stop."""

import numpy as np
from komorebi.bench import power

from prism.check.threads import account_read, compare
from prism.check.threads.card import closed, run_frame
from prism.check.threads.sun import shadow_host
from prism.program.dispatch import thread as dispatch

MS = 1e-3  # the times rows' microseconds as ms
DIGITS = 4
STAGEWISE = "stagewise"
# the dispatcher's times columns as the table names the phases
PHASES = dict(
    zip(dispatch.TIMES, ("count", "sums", "running", "place", "words", "tile"))
)


def clock(card):
    """Card `card`'s AICLK in MHz now."""
    return power.aiclk_mhz(card)


def flat(row, times):
    """A times row's columns `times` as {name: ms}: a layer unit's `<name>.<i>`."""
    out = {}
    for name in times:
        value = row[name]
        if isinstance(value, list):
            out |= {f"{name}.{i}": v * MS for i, v in enumerate(value)}
        else:
            out[name] = value * MS
    return out


def stagewise(loop, camera, frames):
    """`frames` frames of the stage-wise `loop` (stopped after): the first frame's
    picture, each frame's code and whether its picture equals the first's, the times
    rows."""
    codes, same, want = [], [], None
    for _ in range(frames):
        frame = loop.frame(camera, picture=True)
        codes.append(frame.code)
        if frame.code:
            break
        if want is None:
            want = frame.picture
        same.append(bool(np.array_equal(frame.picture, want)))
    loop.stop()
    times = list(loop.loaded.layout.times)
    rows = [flat(row, times) for row in loop.times()[-len(codes) :]]
    return want, {"codes": codes, "same_as_first": same, "rows": rows}


def threads(loop, camera, frames, policy, want, mhz=None):
    """`frames` frames of the threads' `loop` at `policy` (stopped after), each
    picture judged against `want`: codes, judged (equal, pixels differing), times
    rows; with the account each frame's account and records, the choice's words."""
    codes, judged, kept, held = [], [], [], []
    before = None
    for _ in range(frames):
        done = run_frame(loop, camera, 0, policy)
        codes.append(done["code"])
        if done["picture"] is None:
            break
        one = compare.pictures(done["picture"], want)
        judged.append({"equal": one["equal"], "pixels": one.get("pixels_differ", 0)})
        words = account_read.pages(loop)
        if words is not None:
            before = np.zeros(len(words), np.int64) if before is None else before
            rows, before, lost = account_read.records(words, before)
            blocks = account_read.blocks(words)
            views = sorted({int(v) & 0xFF for v in rows[:, 1]} or {0})
            one = {v: account_read.summary(blocks, (v,), mhz) for v in views}
            kept.append({"views": one, "lost": lost})
            held.append((rows, blocks))
    stop = closed(loop)
    times = list(loop.loaded.layout.times)
    rows = [flat(row, times) for row in loop.loaded.times()[-len(codes) :]]
    sun = shadow_host(loop)
    trace = loop.loaded.run.trace() if stop is None else None
    out = {
        "codes": codes,
        "judged": judged,
        "rows": rows,
        "stop": stop,
        "sun_passes": None if sun is None else list(sun.passes),
    }
    if kept:
        choice = account_read.choice(loop)
        out["account"] = kept
        out["choice"] = {
            name: choice[:, i].tolist() for i, name in enumerate(account_read.CHOICE)
        }
        out["records"] = held
    if trace is not None:
        out["trace"] = trace.rows
        out["trace_mhz"] = trace.mhz
    return out


def medians(rows, first=1):
    """{column: median ms, min, max} over `rows` from row `first` (the first frame
    apart)."""
    kept = rows[first:] or rows
    out = {}
    for name in kept[-1]:
        values = np.array([row[name] for row in kept if name in row])
        out[name] = [
            round(float(np.median(values)), DIGITS),
            round(float(values.min()), DIGITS),
            round(float(values.max()), DIGITS),
        ]
    return out


def phases(times):
    """The threads' phases {phase: [median, min, max]} of `times` (medians)."""
    return {PHASES[k]: v for k, v in times.items() if k in PHASES}
