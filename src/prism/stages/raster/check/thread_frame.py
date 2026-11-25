"""Frames of the preset `raster` by a Loop, the view's own camera in each: the picture of
the first, the second and the last against prism_reference's vertex-colour frame, the
codes, and the times rows of the last frames."""

import numpy as np

from prism.loop.report import medians
from prism.stages.raster.check.frame import reference_planes
from prism_reference.scene.camera import with_size

FRAMES = 64  # frames a check runs, unless the options say
TIMED = 32  # the last frames whose times rows give the medians
PARTS = ("count", "sum", "hist", "hsum", "middle", "place", "setup", "fill", "frame")
RESULTS = ("slots", "items", "marks", "heavy_tiles")


def pictures_differ(got, want):
    """Pixels whose five planes are not the reference's bit for bit (padded frame)."""
    return int((got.view(np.uint32) != want.view(np.uint32)).any(axis=0).sum())


def check(loop):
    """The preset's frames on `loop` (a prism.loop.Loop): their codes, the pixels that
    differ in the frames checked, the times' medians over the last TIMED rows."""
    frames = int(loop.options.get("frames", FRAMES))
    scene = with_size(loop.scene, loop.size)
    want = reference_planes(scene)
    checked, differ, codes, rows = {0, 1, frames - 1}, {}, [], []
    for number in range(frames):
        frame = loop.frame(scene["camera"], picture=number in checked)
        codes.append(frame.code)
        rows.append(frame.row)
        if frame.code:
            break
        if number in checked:
            differ[number + 1] = pictures_differ(frame.picture, want)
    loop.stop()
    times = [loop.times()[row] for row in rows[-TIMED:]]
    times = [row for row in times if row is not None]
    host = loop.loaded.hosts["raster"]
    return {
        "frames": len(codes),
        "codes": sorted(set(codes)),
        "pixels": int(want[0].size),
        "pixels_differ": differ,
        "covered": int((want[4] >= 0).sum()),
        "tiles": host.held.tiles,
        "cores": host.cores,
        "ms": medians(times, PARTS, RESULTS) if times else {},
    }
