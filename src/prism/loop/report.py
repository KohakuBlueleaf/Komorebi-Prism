"""A loop's record: the median and the least of each time column over the frames asked
for (a layer unit's by layer), their codes, the reloads, retries and sizes; one dict for
prism.check.harness."""

import numpy as np

MS = 1e-3  # a microsecond's


def columns(loop):
    """The time columns and the result columns of the loaded thread's rows."""
    layout = loop.loaded.layout
    return list(layout.times), list(layout.results)


def by_name(row, names):
    """The values of `names` in a times row, a layer unit's split by layer: layer 0's
    under its name, layer i's under `<name>.<i>`."""
    out = {}
    for name in names:
        value = row[name]
        if not isinstance(value, list):
            out[name] = value
            continue
        out[name] = value[0]
        out |= {f"{name}.{layer}": one for layer, one in enumerate(value[1:], 1)}
    return out


def medians(rows, parts, results):
    """The median of each of `parts` over times `rows`, in ms; `results` of the last
    row; a layer unit's by layer (by_name)."""
    rows = [by_name(row, parts + results) for row in rows]
    times = [name for name in rows[-1] if name.split(".")[0] in parts]
    out = {name: float(np.median([row[name] for row in rows])) * MS for name in times}
    return out | {
        name: value for name, value in rows[-1].items() if name.split(".")[0] in results
    }


def record(loop, frames, extra=None):
    """The record of `frames` (Loop.frame's Frames) after loop.stop(): each time
    column's median and least in ms over their rows, the codes, the reloads, the
    retries, the sizes; `extra` merged in."""
    times, _ = columns(loop)
    rows = loop.times()
    asked = [rows[frame.row] for frame in frames if 0 <= frame.row < len(rows)]
    asked = [by_name(row, times) for row in asked if row is not None]
    ms = {}
    for name in dict.fromkeys(name for row in asked for name in row):
        values = [row[name] for row in asked if name in row]
        values = np.array(values, dtype=np.float64) * MS
        if len(values):
            ms[name] = {
                "median": round(float(np.median(values)), 4),
                "least": round(float(values.min()), 4),
            }
    codes = [frame.code for frame in frames]
    return {
        "frames": len(frames),
        "rows": len(asked),
        "codes": sorted(set(codes)),
        "codes_not_0": sum(code != 0 for code in codes),
        "ms": ms,
        "reloads": loop.reloads,
        "retries": loop.retries,
        "frames_retried": sum(frame.retries for frame in frames),
        "frames_reloaded": sum(frame.reloads for frame in frames),
        "sizes": [list(size) for size in loop.sizes],
        **(extra or {}),
    }


def result_at(loop, frame, name):
    """The result column `name` of a frame's row (None when its row was lost)."""
    rows = loop.times()
    row = rows[frame.row] if 0 <= frame.row < len(rows) else None
    return None if row is None else row[name]
