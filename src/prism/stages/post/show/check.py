"""Frames of a pipeline ending in SHOW by a Loop, the view's own camera in each: the
displayed picture of the first, the second and the last (pushed, and the display read
back) against the frame's own colour converted on the host (bit for bit) and against the
reference of the stage before it; the codes; the times rows of the last frames, by
layer."""

import numpy as np

from prism.loop.report import medians
from prism.stages.direct.light.check.thread_frame import lit
from prism.stages.material.texture.model import expect
from prism.stages.post.show.model.table import displayed
from prism.stages.raster.check.frame import reference_planes
from prism.stages.raster.model.frame import decoded
from prism_reference.post.display import to_srgb8
from prism_reference.raster.frames import picture
from prism_reference.scene.camera import with_size
from prism_reference.scene.frame import frame_grid

FRAMES = 64  # frames a check runs, unless the options say
TIMED = 32  # the last frames whose times rows give the medians
PARTS = ("count", "sum", "hist", "hsum", "middle", "place", "setup", "fill", "shade")
PARTS += ("light", "light_glass", "show", "push", "frame")
RESULTS = ("slots", "items", "marks", "heavy_tiles")
KEPT = ("checked", "differ", "share", "max_error", "frame_differ", "later_pieces")


def reference_display(scene):
    """The reference's vertex-colour frame of `scene` (a view at its size) for display
    (H, W, 4) uint8: its colour by to_srgb8, alpha 255."""
    colour = np.moveaxis(reference_planes(scene)[1:4], 0, 2)
    return displayed(picture(colour, scene))


def pixels_differ(got, want):
    """Pixels whose four bytes are not `want`'s."""
    return int((np.asarray(got) != want).any(axis=2).sum())


def vertex_colour(loop, scene):
    """The raster preset's judge: pixels that differ from reference_display."""
    want = reference_display(scene)
    return lambda got: {"pixels_differ": pixels_differ(got, want)}


def shaded(loop, scene):
    """The textured preset's judge: expect.check's report on the shaded reference."""
    materials = loop.options["materials"]

    def judge(got):
        report, _, _ = expect.check(scene, materials, got, to_srgb8)
        return {name: report[name] for name in KEPT}

    return judge


JUDGES = {"raster": vertex_colour, "material.texture": shaded, "direct.light": lit}


def host_display(loop, scene):
    """The frame's colour (the first layer's frame, every layer in it) read back and
    converted on the host: what the display holds, (H, W, 4) uint8."""
    raster = loop.loaded.hosts["raster"]
    words = np.concatenate(
        [
            loop.loaded.session.read(tensor)[0].view(np.uint32).reshape(-1)
            for tensor in raster.layers["opaque"]["frame"]
        ]
    )
    planes = decoded(words, *frame_grid(loop.size))
    return displayed(picture(np.moveaxis(planes[1:4], 0, 2), scene))


def parts_of(rows):
    """The PARTS the pipeline's times rows hold."""
    return tuple(part for part in PARTS if part in rows[-1])


def check(loop):
    """The preset's frames on `loop` (a prism.loop.Loop): their codes; in the frames
    checked, the pushed picture and the display read back against the host's
    conversion of the frame and against the reference; the times' medians."""
    frames = int(loop.options.get("frames", FRAMES))
    scene = with_size(loop.scene, loop.size)
    names = [i.name for i in loop.loaded.assembled.pipeline.implementations]
    judge = JUDGES[names[-2]](loop, scene)
    host = loop.loaded.hosts["post.show"]
    checked, pictures, numbers, codes, rows = {0, 1, frames - 1}, {}, {}, [], []
    for number in range(frames):
        frame = loop.frame(scene["camera"], picture=number in checked)
        codes.append(frame.code)
        rows.append(frame.row)
        if frame.code:
            break
        if number in checked:
            got, want = frame.picture, host_display(loop, scene)
            pictures[number + 1] = got
            numbers[number + 1] = {
                "host_differ": pixels_differ(got, want),
                "read_back_differ": pixels_differ(host.display(loop.loaded), want),
            } | judge(got)
    loop.stop()
    times = [loop.times()[row] for row in rows[-TIMED:]]
    times = [row for row in times if row is not None]
    first, *rest = sorted(pictures) or [None]
    return {
        "frames": len(codes),
        "codes": sorted(set(codes)),
        "pipeline": names,
        "pictures": numbers,
        "same_picture": all(np.array_equal(pictures[first], pictures[n]) for n in rest),
        "push": host.push,
        "tiles": host.held.tiles,
        "cores": host.cores,
        "ms": medians(times, parts_of(times), RESULTS) if times else {},
    }
