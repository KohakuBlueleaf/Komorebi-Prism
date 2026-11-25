"""Frames of a pipeline with the field's update by a Loop: each sun of the options set
in turn (the loop sends the sun's pass, then the update, before the next frame), the
field the card wrote against the reference's for the card's shadow map, the first and
last pictures against the reference's lit frame at that sun; after the stop the scale
words and the times."""

import numpy as np

from prism.loop.report import medians
from prism.stages.direct.light.check.thread_frame import PARTS, lit
from prism.stages.indirect.field_update.check import field_numbers, update_times
from prism.stages.indirect.field_update.check import verdict as field_verdict
from prism.stages.indirect.field_update.model.numbers import F32
from prism.stages.indirect.field_update.model.results import (
    expected,
    field_texels,
    times,
)
from prism.stages.material.texture.check.thread_frame import RESULTS
from prism_reference.indirect.field.pack import PACK_BITS
from prism_reference.scene.camera import with_size

SUN, UPDATE, LIGHT = "direct.shadow_pcf", "indirect.field_update", "direct.light"
CONTROL = f"{SUN}.sun"
SUNS = ((120.0, 40.0), (200.0, 30.0))  # the suns set, unless the options say
FRAMES = 16  # frames a sun, unless the options say
TIMED = 32  # the last frames whose times rows give the medians


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


def at_sun(loop, sun, frames, scene):
    """The sun set, `frames` frames: their codes and rows, the field after the
    first, the first and last pictures judged."""
    loop.set(CONTROL, sun)
    judge = lit(loop, scene)
    host = loop.loaded.hosts[UPDATE]
    out = {"sun": list(sun), "codes": [], "pictures": {}}
    rows, first = [], None
    for number in range(frames):
        frame = loop.frame(scene["camera"], picture=number in (0, frames - 1))
        out["codes"].append(frame.code)
        rows.append(frame.row)
        if frame.code:
            break
        if number == 0:
            out |= field_now(loop)
            out["updates"] = host.given["updates"]
        if frame.picture is not None:
            out["pictures"][number + 1] = judge(frame.picture)
            first = frame.picture if first is None else first
            out["same_picture"] = bool(np.array_equal(first, frame.picture))
    return out, rows


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


def check(loop):
    """Each sun of the options' `suns` in turn (its frames, the field, the pictures);
    after the stop the update's codes and scale words, the times' medians."""
    frames = int(loop.options.get("frames", FRAMES))
    scene = with_size(loop.scene, loop.size)
    suns, rows = [], []
    for sun in loop.options.get("suns") or SUNS:
        one, more = at_sun(loop, tuple(sun), frames, scene)
        suns.append(one)
        rows += more
        if any(one["codes"]):
            break
    loop.stop()
    host = loop.loaded.hosts[UPDATE]
    updates = times(loop.loaded.region("field_times"))
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
        "ms": medians(timed, PARTS, RESULTS) if timed else {},
    }
