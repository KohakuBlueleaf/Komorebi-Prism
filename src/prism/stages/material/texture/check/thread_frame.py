"""Frames of the preset `textured` by a Loop, the view's own camera in each: the picture
of the first and of the last against prism_reference's shaded frame (model/expect.check),
the codes, and the times rows of the last frames, by layer."""

import numpy as np

from prism.loop.report import medians
from prism.stages.material.texture.model import expect
from prism_reference.post.display import to_srgb8
from prism_reference.scene.camera import with_size

FRAMES = 16  # frames a check runs, unless the options say
TIMED = 32  # the last frames whose times rows give the medians
# the parts by layer (the frame's once): the raster stage's, then SHADE
PARTS = ("count", "sum", "hist", "hsum", "middle", "place", "setup", "fill", "shade")
PARTS += ("frame",)
RESULTS = ("slots", "items", "marks", "heavy_tiles")
KEPT = ("checked", "differ", "share", "max_error", "frame_differ", "later_pieces")


def reference_picture(scene, materials):
    """The reference's shaded frame of `scene` (a view at its size) on `materials`, as
    the 8-bit picture expect.check compares with."""
    _, want, _ = expect.check(scene, materials, np.zeros((1, 1, 3), np.uint8), to_srgb8)
    return want


def check(loop):
    """The preset's frames on `loop` (a prism.loop.Loop, its options' materials): their
    codes, the first and last pictures against the reference and against each other,
    the times' medians over the last TIMED rows by layer."""
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
    loop.stop()
    reports, first = {}, None
    for number, got in pictures.items():
        if first is not None and np.array_equal(got, pictures[first]):
            reports[number] = reports[first]
            continue
        report, _, _ = expect.check(scene, materials, got, to_srgb8)
        reports[number], first = {name: report[name] for name in KEPT}, number
    times = [loop.times()[row] for row in rows[-TIMED:]]
    times = [row for row in times if row is not None]
    raster, texture = loop.loaded.hosts["raster"], loop.loaded.hosts["material.texture"]
    return {
        "frames": len(codes),
        "codes": sorted(set(codes)),
        "layers": list(texture.order),
        "pictures": reports,
        "same_picture": len(pictures) > 1
        and np.array_equal(*(pictures[n] for n in sorted(pictures)[:2])),
        "tiles": raster.held.tiles,
        "cores": raster.cores,
        "ms": medians(times, PARTS, RESULTS) if times else {},
    }
