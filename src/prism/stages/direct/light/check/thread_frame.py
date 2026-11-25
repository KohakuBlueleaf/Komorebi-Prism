"""Frames of the preset `lit` by a Loop, the view's own camera in each: the picture of
the first and of the last against prism_reference's lit frame at the loop's sun, tone
and terms (model/expect.light_check), the sun's map when its pass ran, the codes, the
units that ran in the last frame's row, and the times rows' medians by layer."""

import numpy as np

from prism.loop.report import medians
from prism.stages.direct.light.model.expect import light_check
from prism.stages.direct.shadow_pcf.check.sun_map import sun_map
from prism.stages.material.texture.check.thread_frame import RESULTS
from prism_reference.direct.frame import TERMS
from prism_reference.direct.lights import moved
from prism_reference.scene.camera import with_size

FRAMES = 16  # frames a check runs, unless the options say
TIMED = 32  # the last frames whose times rows give the medians
LIGHT, SUN = "direct.light", "direct.shadow_pcf"
# the parts by layer (the frame's once): the raster stage's, SHADE, then the frame's
PARTS = ("count", "sum", "hist", "hsum", "middle", "place", "setup", "fill", "shade")
PARTS += ("light", "light_glass", "show", "push", "frame")
SEQUENCE = ("count", "setup", "fill", "shade", "light", "light_glass", "show", "push")
KEPT = ("checked", "later_pieces", "share_over_2", "share_over_4", "share_over_8")
KEPT += ("max_error", "glass_in_front", "band", "outside_band")  # those a report has


def lights_now(loop, scene):
    """The lights the frames of `scene` are lit with, under the loop's tone: at the
    loop's sun the reference's moved lights (the shadow map rebuilt), else their own;
    the field of the option `bounces` when given."""
    host = loop.loaded.hosts[LIGHT]
    options = loop.loaded.options
    sun = options.get("sun")
    lights = host.lights
    if sun is not None:
        lights = moved(host.lights, scene, loop.options["materials"], *sun)
    if "bounces" in options:
        lights = {**lights, "bounces": options["bounces"]}
    return {**lights, **host.tone}


def terms_now(host):
    """The terms LIGHT's table lights with: the host's, without indirect while its
    switch is off."""
    return tuple(t for t in host.terms if t != "indirect" or host.indirect)


def reference_picture(scene, materials, lights, terms=TERMS):
    """The reference's lit frame of `scene` (a view at its size) as the 8-bit picture
    light_check compares with."""
    got = np.zeros((1, 1, 4), np.uint8)
    return light_check(scene, materials, lights, got, terms)[1]


def reference(loop, scene):
    """The picture a frame of `scene` (a view at its size) is compared with: its lit
    frame on the loop's materials and lights at the loop's sun, tone and terms."""
    terms = terms_now(loop.loaded.hosts[LIGHT])
    return reference_picture(
        scene, loop.options["materials"], lights_now(loop, scene), terms
    )


def lit(loop, scene):
    """The preset `lit`'s judge for a pipeline ending in SHOW: light_check's report on
    the reference at the loop's sun, tone and terms."""
    materials, lights = loop.options["materials"], lights_now(loop, scene)
    terms = terms_now(loop.loaded.hosts[LIGHT])

    def judge(got):
        report, _ = light_check(scene, materials, lights, got, terms)
        return {name: report[name] for name in KEPT if name in report}

    return judge


def sequence(row, layers):
    """The units' parts that ran in a times row, in the frame's order: a layer's by
    name (`<part>.<layer>`), the frame's once."""
    ran = []
    for part in SEQUENCE:
        value = row.get(part)
        if isinstance(value, list):
            ran += [f"{part}.{layers[i]}" for i, one in enumerate(value) if one]
        elif value:
            ran.append(part)
    return ran


def check(loop):
    """The preset's frames on `loop` (its options' materials): their codes, the first
    and last pictures against the reference and against each other, the sun's map when
    its pass ran, the last row's sequence, the times' medians over the last TIMED rows
    by layer."""
    frames = int(loop.options.get("frames", FRAMES))
    scene = with_size(loop.scene, loop.size)
    materials = loop.options["materials"]
    checked, pictures, codes, rows = {0, frames - 1}, {}, [], []
    for number in range(frames):
        frame = loop.frame(scene["camera"], picture=number in checked)
        codes.append(frame.code)
        rows.append(frame.row)
        if frame.code:
            break
        if number in checked:
            pictures[number + 1] = frame.picture
    sun = loop.loaded.hosts[SUN]
    map_report = sun_map(loop, scene) if sun.passes else None
    loop.stop()
    light = loop.loaded.hosts[LIGHT]
    lights, terms = lights_now(loop, scene), terms_now(light)
    reports, first = {}, None
    for number, got in pictures.items():
        if first is not None and np.array_equal(got, pictures[first]):
            reports[number] = reports[first]
            continue
        report, _ = light_check(scene, materials, lights, got, terms)
        reports[number], first = {
            name: report[name] for name in KEPT if name in report
        }, number
    times = [loop.times()[row] for row in rows[-TIMED:]]
    times = [row for row in times if row is not None]
    return {
        "frames": len(codes),
        "codes": sorted(set(codes)),
        "layers": list(light.order),
        "sun": list(loop.loaded.options.get("sun") or ()),
        "tone": dict(light.tone),
        "terms": list(terms),
        "pictures": reports,
        "same_picture": len(pictures) > 1
        and np.array_equal(*(pictures[n] for n in sorted(pictures)[:2])),
        "sequence": sequence(times[-1], light.order) if times else [],
        "sun_map": map_report,
        "sun_passes": sun.passes,
        "sun_times": sun.times(loop.loaded),
        "cores": light.cores,
        "ms": medians(times, PARTS, RESULTS) if times else {},
    }
