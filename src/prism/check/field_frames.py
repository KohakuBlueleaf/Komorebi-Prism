"""Frames of a pipeline with the field's update by a Loop: each sun of the options set
in turn (the loop sends the sun's pass, then the update, before the next frame; or the
update beside the frames, swapped in between two), the field the card wrote against the
reference's for the card's shadow map, the first and last pictures and the first after
the update against the reference's lit frame at that sun; the frames drawn during the
update, the gaps between frames' ends on the host; after the stop the scale words, the
times and the core steps."""

import hashlib
import time

import numpy as np

from prism.core.unit import BESIDE
from prism.loop.report import columns, medians
from prism.program.loaded import MICROSECONDS
from prism.stages.direct.light.check.thread_frame import lit
from prism.stages.indirect.field_update.check import field_numbers, update_times
from prism.stages.indirect.field_update.check import verdict as field_verdict
from prism.stages.indirect.field_update.model.numbers import F32
from prism.stages.indirect.field_update.model.results import (
    expected,
    field_texels,
    times,
)
from prism_reference.indirect.field.pack import PACK_BITS
from prism_reference.scene.camera import with_size

SUN, UPDATE, LIGHT = "direct.shadow_pcf", "indirect.field_update", "direct.light"
CONTROL = f"{SUN}.sun"
SUNS = ((120.0, 40.0), (200.0, 30.0))  # the suns set, unless the options say
FRAMES = 16  # frames a sun, unless the options say
TIMED = 32  # the last frames whose times rows give the medians
MS = 1e3
TICK_MS = MICROSECONDS / MS  # a timer tick's


def units_of(scale):
    """LIGHT's three units of a field's `scale`: (1 / max code)^2 x scale, float32 in
    the card's order."""
    units = [F32(1) / F32((1 << bits) - 1) for bits in PACK_BITS]
    return np.array([(unit * unit) * F32(scale) for unit in units], F32)


def field_now(loop):
    """The field in the light pages against the reference's for the update's lights
    with the card's shadow map: field_check's numbers and the scale's."""
    host = loop.loaded.hosts[UPDATE]
    lights = {**host.lights, "shadow_map": loop.loaded.hosts[SUN].map(loop.loaded)}
    want = expected(lights, host.model, host.bounces)
    got = field_texels(host.field_pages(), host.model)
    scale = float(host.given["scale"])
    return {
        "field": field_numbers(got, want["texels"]),
        "scale": {
            "card": scale,
            "reference": float(want["scale"]),
            "relative": abs(scale - float(want["scale"])) / float(want["scale"]),
        },
    }


def digest(picture):
    """A picture's bytes' sha256, hex."""
    return hashlib.sha256(np.ascontiguousarray(picture).tobytes()).hexdigest()


def apart(one, other):
    """Two pictures' difference: bytes and pixels that differ, the largest byte
    difference; None without both."""
    if one is None or other is None:
        return None
    gap = np.abs(one.astype(np.int16) - other.astype(np.int16))
    return {
        "bytes_different": int(np.count_nonzero(gap)),
        "pixels_different": int(
            np.count_nonzero(gap.reshape(-1, gap.shape[-1]).any(1))
        ),
        "largest": int(gap.max(initial=0)),
    }


def at_sun(loop, sun, frames, scene, before=None):
    """The sun set, `frames` frames: their codes and rows, whether each was drawn
    before the update's field was in (and the gap since the frame before on the host,
    with and without the reads of pictures between), the field and the picture of the
    first frame after it, the first and last pictures judged; the first frame drawn
    during the update against `before` (the last picture at the sun before) and the
    first after. The last picture besides. Judged after the frames."""
    started = time.perf_counter()
    loop.set(CONTROL, sun)
    host = loop.loaded.hosts[UPDATE]
    made = host.given["updates"]
    out = {"sun": list(sun), "codes": [], "pictures": {}, "frames": []}
    rows, kept, read, during, swap = [], {}, 0.0, None, None
    for number in range(frames):
        frame = loop.frame(scene["camera"])
        ended = time.perf_counter()
        out["codes"].append(frame.code)
        rows.append(frame.row)
        if frame.code:
            break
        old = host.given["updates"] == made
        gap = (ended - started) * MS
        out["frames"].append(
            {"row": frame.row, "during": old, "gap_ms": gap, "net_ms": gap - read}
        )
        read, started = 0.0, ended
        if not old and swap is None:
            swap = number
            out["host_ms"] = host.last_ms
        if number in (0, frames - 1) or number == swap or (old and during is None):
            kept[number] = loop.picture().copy()
            read = (time.perf_counter() - ended) * MS
            during = number if old and during is None else during
    judge = lit(loop, scene)
    for number in (0, frames - 1):
        if number in kept:
            picture = kept[number]
            out["pictures"][number + 1] = judge(picture) | {"sha256": digest(picture)}
            out["same_picture"] = bool(np.array_equal(kept[0], picture))
    if swap is not None:
        out["swap_frame"] = swap + 1
        out["swap_picture"] = digest(kept[swap])
        out |= field_now(loop)
        out["updates"] = host.given["updates"]
        held = kept.get(during)
        out["during_against"] = {
            "before": apart(held, before),
            "after": apart(held, kept[swap]),
        }
    return out, rows, kept.get(frames - 1)


def scale_words(rows, suns):
    """Each update's row: the scale field_scale returned against the row's, and the
    host's units of it against the row's words, bit for bit."""
    out = []
    for row, sun in zip(rows, suns, strict=False):
        given = F32(sun.get("scale", {}).get("card", np.nan))
        out.append(
            {
                "scale_equal": bool(
                    given.view(np.uint32) == F32(row["scale"]).view(np.uint32)
                ),
                "units_equal": bool(
                    np.array_equal(
                        units_of(row["scale"]).view(np.uint32),
                        np.array(row["unit"], F32).view(np.uint32),
                    )
                ),
            }
        )
    return out


def frame_times(loop, suns):
    """Each sun's frames given their card time, the director's resubmits (core
    commands submitted again after a busy rejection) and the time waited for the wake
    before them since the frame before, and the frame's longest such wait, from their
    times rows (ms); the frames drawn during the update apart: their count, card times,
    resubmits and waits, against the steady frame's (the frames after the update)."""
    times = loop.times()
    kept = {"resubmits": 0, "wake_ticks": 0}
    for one in suns:
        for frame in one["frames"]:
            row = times[frame["row"]] if frame["row"] < len(times) else None
            frame["card_ms"] = None if row is None else row["frame"] / MS
            frame["wake_most_ms"] = 0.0 if row is None else row["wake_most"] * TICK_MS
            for name, total in kept.items():
                now = total if row is None else row[name]
                frame[name], kept[name] = now - total, now
            frame["wake_ms"] = frame.pop("wake_ticks") * TICK_MS
        during = [f for f in one["frames"] if f["during"]]
        after = [f for f in one["frames"][1:] if not f["during"]]
        steady = [f["card_ms"] for f in after]
        steady_gaps = [f["net_ms"] for f in after]
        one["during"] = {
            "frames": len(during),
            "card_ms": [f["card_ms"] for f in during],
            "resubmits": sum(f["resubmits"] for f in during),
            "resubmits_after": sum(f["resubmits"] for f in after),
            "wake_ms": sum(f["wake_ms"] for f in during),
            "wake_most_ms": max((f["wake_most_ms"] for f in during), default=0.0),
            "longest_gap_ms": max((f["gap_ms"] for f in during), default=None),
            "longest_net_ms": max((f["net_ms"] for f in during), default=None),
            "steady_card_ms": float(np.median(steady)) if steady else None,
            "steady_gap_ms": float(np.median(steady_gaps)) if steady_gaps else None,
        }


def update_rows(loop):
    """The update's times rows, read after the stop: the job thread's region when the
    update is a graph (the threads' form), else the field update's thread region."""
    graph = getattr(loop.loaded.hosts[UPDATE], "graph", None)
    raw = loop.loaded.region("field_times") if graph is None else graph.times()
    return times(raw)


def check(loop):
    """Each sun of the options' `suns` in turn (its frames, the field, the pictures);
    after the stop the update's codes and scale words, the frames' card times, the
    times' medians and the core steps of a cluster beside the frames'."""
    frames = int(loop.options.get("frames", FRAMES))
    scene = with_size(loop.scene, loop.size)
    suns, rows, last = [], [], None
    for sun in loop.options.get("suns") or SUNS:
        one, more, last = at_sun(loop, tuple(sun), frames, scene, last)
        suns.append(one)
        rows += more
        if any(one["codes"]):
            break
    loop.stop()
    frame_times(loop, suns)
    steps = loop.loaded.steps(BESIDE) if BESIDE in loop.loaded.layouts else None
    host = loop.loaded.hosts[UPDATE]
    updates = update_rows(loop)
    for one, row in zip(suns, updates, strict=False):
        judged = {
            "codes": [c for c in one["codes"] if c],
            "row_codes": [row["code"]],
            "scene": host.scene,
            "bounces": host.bounces,
            "stepped": False,
            **{k: one[k] for k in ("field", "scale") if k in one},
        }
        one["verdict"] = field_verdict(judged)
    timed = [loop.times()[row] for row in rows[-TIMED:]]
    timed = [row for row in timed if row is not None]
    return {
        "bounces": host.bounces,
        "terms": list(loop.loaded.hosts[LIGHT].terms),
        "suns": suns,
        "scale_words": scale_words(updates, suns),
        "updates": [update_times(row) | {"code": row["code"]} for row in updates],
        "sun_passes": loop.loaded.hosts[SUN].passes,
        "sun_times": loop.loaded.hosts[SUN].times(loop.loaded),
        "ms": medians(timed, *columns(loop)) if timed else {},
        "core_steps": steps,
    }
