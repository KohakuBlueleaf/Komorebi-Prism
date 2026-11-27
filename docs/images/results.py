"""Draws docs/images/results-{light,dark}.svg: the renderer's frame (gi_threads) against
its stage-wise form (gi less its push) on ten scenes, and a glTF file's load to its first
picture, cold and warm, on three artists' scenes.

usage: python docs/images/results.py [output folder]    (the standard library only)

The numbers are copied from measurements/gi_threads/README.md (the table "The frame")
and measurements/open/README.md (the table of seconds to the first picture of "The waste
cut", after).
"""

import sys

from draw import Svg, write

W = 830
# scene (view), gi less push, gi_threads: ms
FRAME = (
    ("sponza", 22.447, 18.610),
    ("bistro_interior", 33.282, 24.182),
    ("breakfast_room", 18.422, 15.303),
    ("salle_de_bain", 21.842, 19.189),
    ("modern_hall", 23.966, 18.639),
    ("modern_living_room", 25.647, 18.196),
    ("classroom_a1c62e93f7", 21.394, 19.170),
    ("lynxsdesign_411c9daef8", 53.802, 49.474),
    ("italian_flat_97f97a20ba", 48.023, 42.224),
    ("lynxsdesign_a01894bbb8", 94.159, 102.094),
)
# scene (triangles), cold, warm: seconds to the first picture
LOAD = (
    ("classroom", "1.25 M triangles", 62.4, 7.1),
    ("hidden_alley", "9.0 M triangles", 104.1, 16.2),
    ("lynxsdesign", "29.8 M triangles", 133.7, 21.3),
)


def panel(s, y, h, title, colour, note=""):
    c = s.c
    s.rect(16, y, W - 32, h, c["box"], c["line"], layer=0)
    s.text(30, y + 22, title, 14, c[colour][0], True)
    if note:
        s.text(W - 30, y + 22, note, 12, c["mute"], anchor="end")


def axis(s, x0, x1, y, top, most, step, unit):
    """Grid lines and ticks from 0 to `most` every `step`, labels under `y`."""
    c = s.c
    k = (x1 - x0) / most
    v = 0
    while v <= most + 1e-9:
        x = x0 + v * k
        s.rule(x, top, x, y, 0.5 if v else 1.0, None if v == 0 else "2 3")
        s.text(x, y + 14, f"{v:g}", 11, c["mute"], anchor="middle")
        v += step
    s.text(x1, y + 30, unit, 11, c["mute"], anchor="end")
    return k


def legend(s, x, y, items):
    c = s.c
    for name, colour in items:
        s.rect(x, y - 10, 12, 12, c[colour][1], c[colour][0], rx=2, sw=1)
        s.text(x + 18, y, name, 11.5, c["fg"])
        x += 30 + 6.6 * len(name)


def frame_panel(s, top):
    c = s.c
    row, bar = 34, 12
    h = 96 + row * len(FRAME) + 40
    panel(
        s,
        top,
        h,
        "The frame: gi_threads against gi less its push",
        "w",
        "1,920 x 1,080, one P150A, ms",
    )
    legend(
        s, 30, top + 46, (("gi, stage-wise, less its push", "a"), ("gi_threads", "w"))
    )
    s.text(W - 30, top + 46, "gi_threads / gi", 11.5, c["mute"], anchor="end")
    x0, x1 = 212, W - 104
    y0 = top + 62
    k = axis(s, x0, x1, y0 + row * len(FRAME) + 4, y0, 110, 10, "ms")
    for i, (name, gi, threads) in enumerate(FRAME):
        y = y0 + i * row + 4
        s.text(x0 - 10, y + bar + 4, name, 11.5, c["fg"], anchor="end")
        for j, (value, colour) in enumerate(((gi, "a"), (threads, "w"))):
            yy = y + j * (bar + 2)
            edge, mid, _ = c[colour]
            s.rect(x0, yy, value * k, bar, mid, edge, rx=1, sw=1)
            s.text(x0 + value * k + 5, yy + bar - 2, f"{value:.1f}", 10.5, edge)
        ratio = threads / gi
        s.text(
            W - 30, y + bar + 4, f"{ratio:.2f}", 11.5, c["fg"], ratio < 1, anchor="end"
        )
    s.text(
        30,
        top + h - 14,
        "The median over frames 2 to 64 at the view's camera, then over "
        "three runs; every gi_threads picture equal to gi's, byte for byte.",
        11,
        c["mute"],
    )
    return top + h


def load_panel(s, top):
    c = s.c
    row, bar = 42, 14
    h = 96 + row * len(LOAD) + 36
    panel(
        s,
        top,
        h,
        "A glTF file's load: seconds to the first picture",
        "a",
        "prism_cli open, lit, 1,920 x 1,080",
    )
    legend(
        s, 30, top + 46, (("cold: converted, program built", "a"), ("warm: found", "r"))
    )
    x0, x1 = 212, W - 104
    y0 = top + 62
    k = axis(s, x0, x1, y0 + row * len(LOAD) + 4, y0, 140, 20, "s")
    for i, (name, tris, cold, warm) in enumerate(LOAD):
        y = y0 + i * row + 6
        s.text(x0 - 10, y + 12, name, 11.5, c["fg"], anchor="end")
        s.text(x0 - 10, y + 26, tris, 11, c["mute"], anchor="end")
        for j, (value, colour) in enumerate(((cold, "a"), (warm, "r"))):
            yy = y + j * (bar + 2)
            edge, mid, _ = c[colour]
            s.rect(x0, yy, value * k, bar, mid, edge, rx=1, sw=1)
            s.text(x0 + value * k + 5, yy + bar - 3, f"{value:.1f}", 10.5, edge)
    s.text(
        30,
        top + h - 14,
        "One P150A, 24 CPUs of the host, 2026-11-27: the host part (the "
        "conversion, the lights) and the card part added.",
        11,
        c["mute"],
    )
    return top + h


def results(theme):
    s = Svg(theme, "The measured frame and load", W)
    y = frame_panel(s, 12)
    y = load_panel(s, y + 12)
    return s.finish(y + 12)


if __name__ == "__main__":
    write({"results": results}, sys.argv[1] if len(sys.argv) > 1 else None)
