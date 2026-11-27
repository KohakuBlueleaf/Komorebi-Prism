"""Draws docs/images/resident-{light,dark}.svg: what tile-resident means. Above, the
stage-wise form: each step is a command on every core, and between two commands the
frame's planes are written to DRAM and read back. Below, the threads' form: the core
that took a tile runs its steps one after another with the tile's planes in its L1,
reads only lists and pages, and writes only the tile's display page.

usage: python docs/images/resident.py [output folder]    (the standard library only)

Numbers, Sponza's overview, 1,920 x 1,080, lit, all cores, a frame: the stage-wise
commands' times and bytes written and read from measurements/account (lit, sponza,
1,920 x 1,080: fill, shade and both layers' forms added, light, show, push); the
threads' bytes by path and pack's step times from measurements/threads_account. Plane
sizes: frame.visibility and frame.surface, 20 tiles of 4,096 bytes each
(docs/internals/program/work.md).
"""

import sys

from draw import Svg, chip, write

FW = 880

COMMANDS = (
    ("FILL", "visibility", 2.397, "w", 83.56, None),
    ("SHADE", "material", 6.061, "a", 98.89, 320.58),
    ("LIGHT", "light", 3.099, "y", 25.07, 174.12),
    ("SHOW", "display", 1.542, "p", 8.36, 25.07),
)


def grid(s, x, y, colour, cell=6, gap=1.5):
    """The 120 cores as a 12 x 10 block, every one busy."""
    c = s.c
    for r in range(10):
        for k in range(12):
            s.rect(
                x + k * (cell + gap) + (3 if k >= 6 else 0),
                y + r * (cell + gap),
                cell,
                cell,
                c[colour][1],
                rx=1,
            )


def dram(s, x, y, w, h, text):
    c = s.c
    s.rect(x, y, w, h, c["dram"], rx=4, layer=0)
    s.text(x + 10, y + 17, text, 12, c["fg"], True)


def stagewise(s, top):
    c = s.c
    s.text(
        16,
        top + 18,
        "stage-wise (lit): each step a command on all 120 cores; "
        "the planes go to DRAM and back between them",
        13,
        c["g"][0],
        True,
    )
    y = top + 34
    bw, gapx = 150, 52
    x0 = 16
    dy = y + 196
    dram(
        s,
        16,
        dy,
        FW - 32,
        28,
        "DRAM: the frame's planes, written whole by one "
        "command, read whole by the next",
    )
    xs = []
    for i, (name, step, ms, colour, wrote, read) in enumerate(COMMANDS):
        x = x0 + i * (bw + gapx)
        xs.append(x)
        s.rect(x, y, bw, 150, c[colour][2], c[colour][0], rx=6, sw=1.4)
        s.text(x + 10, y + 19, name, 13, c[colour][0], True)
        s.text(x + bw - 10, y + 19, f"{ms:.3f} ms", 12, c["fg"], True, anchor="end")
        s.text(x + 10, y + 35, f"the {step} of every tile", 11, c["fg"])
        grid(s, x + 10, y + 46, colour)
        s.text(x + 10, y + 132, "every core, then waits", 11, c["mute"])
        s.text(x + 10, y + 145, "for the slowest", 11, c["mute"])
        # written down to DRAM
        wx = x + bw - 12
        s.line(wx, y + 152, wx, dy - 2, colour, 2.2)
        s.text(
            wx - 6,
            y + 186,
            f"{wrote:.2f} MB written",
            11.5,
            c[colour][0],
            True,
            anchor="end",
        )
        if read:
            rx = x + 12
            s.line(rx, dy - 2, rx, y + 152, "g", 1.8)
            s.text(rx + 6, y + 168, f"{read:.2f} MB read", 11.5, c["fg"], True)
    # push to the host
    px = xs[-1] + bw + 14
    s.rect(px, y, FW - 16 - px, 150, c["box"], c["rule"], rx=6, sw=1.2, dash="5 3")
    s.text(px + 8, y + 19, "PUSH", 13, c["fg"], True)
    s.text(px + 8, y + 37, "0.564 ms", 12, c["fg"], True)
    s.text(px + 8, y + 55, "the picture", 11, c["mute"])
    s.text(px + 8, y + 69, "to the host", 11, c["mute"])
    s.line(px + 24, dy - 2, px + 24, y + 152, "g", 1.8)
    s.text(px + 30, y + 168, "8.36 MB", 11.5, c["fg"], True)
    return dy + 28, xs


def resident(s, top):
    c = s.c
    s.text(
        16,
        top + 18,
        "tile-resident (lit_threads): one core runs every step of the "
        "tile it took; the planes stay in its L1",
        13,
        c["r"][0],
        True,
    )
    y = top + 34
    cw = 600
    s.rect(16, y, cw, 190, c["box"], c["r"][0], rx=6, sw=1.4, layer=0)
    s.text(28, y + 19, "one Tensix core, one tile thread", 13, c["r"][0], True)
    s.text(
        16 + cw - 12,
        y + 19,
        "pack's ms a frame a core, the cores' median",
        11,
        c["mute"],
        anchor="end",
    )
    steps = (
        ("visibility", 2.77, "w"),
        ("material_lit", 4.91, "a"),
        ("light", 2.93, "y"),
        ("post", 0.05, "p"),
    )
    x0, span = 40, cw - 60
    per = (span - 3 * 10 - 60) / sum(ms for _, ms, _ in steps[:3])
    xs = {}
    x = x0
    for name, ms, colour in steps:
        w = 60 if name == "post" else ms * per
        chip(s, x, y + 32, w, 40, name, colour, f"{ms:.2f} ms", size=12)
        xs[name] = (x, x + w)
        if name != "visibility":
            s.line(x - 9, y + 52, x - 1, y + 52, colour, 1.6)
        x += w + 10
    # L1 and the planes
    ly = y + 88
    s.text(28, ly + 2, "L1", 12, c["fg"], True)
    planes = (
        (
            "frame.visibility",
            "visibility",
            "post",
            "20 x 4 KiB: depth, colour, triangle, each layer",
        ),
        ("frame.surface", "material_lit", "light", "20 x 4 KiB: the lit surfaces"),
    )
    for k, (name, first, last, sub) in enumerate(planes):
        a, b = xs[first][0], xs[last][1]
        yy = ly + 10 + k * 34
        s.rect(a, yy, b - a, 26, c["y"][2], c["y"][0], rx=4, sw=1.2)
        s.text(a + 8, yy + 17, name, 12, c["fg"], True, mono=True)
        s.text(a + 140, yy + 17, sub, 11, c["mute"])
    s.text(
        40,
        y + 180,
        "nothing of the planes is written to DRAM between the steps",
        11.5,
        c["r"][0],
        True,
    )
    # DRAM below
    dy = y + 236
    dram(
        s,
        16,
        dy,
        FW - 32,
        28,
        "DRAM: the scene's lists and pages in; one display " "page a tile out",
    )
    # in: lists and pages
    lx = xs["visibility"][0] + 30
    s.line(lx, dy - 2, lx, y + 74, "g", 1.8)
    s.text(lx + 6, dy - 26, "lists", 11.5, c["fg"], True)
    s.text(lx + 6, dy - 12, "83.48 MB read", 11, c["mute"])
    gx = xs["material_lit"][0] + 60
    s.line(gx, dy - 2, gx, y + 74, "g", 1.8)
    s.line(xs["light"][0] + 30, dy - 2, xs["light"][0] + 30, y + 74, "g", 1.8)
    s.text(gx + 6, dy - 26, "texture and light pages asked", 11.5, c["fg"], True)
    s.text(gx + 6, dy - 12, "276.41 MB read", 11, c["mute"])
    ox = xs["post"][0] + 30
    s.line(ox, y + 74, ox, dy - 2, "r", 2.4)
    s.text(ox + 8, dy - 26, "8.36 MB", 12, c["r"][0], True)
    s.text(ox + 8, dy - 12, "written", 11, c["mute"])
    # right: the threads of a frame
    rx = 16 + cw + 18
    s.text(rx, y + 14, "x 2,040 tile threads", 13, c["fg"], True)
    s.text(rx, y + 32, "a frame, each on the core", 11.5, c["fg"])
    s.text(rx, y + 46, "that asks next", 11.5, c["fg"])
    for k in range(6):
        s.rect(rx + k * 8, y + 64 + k * 8, 120, 60, c["r"][2], c["r"][0], rx=4, sw=1)
    s.text(rx + 50, y + 116, "a 32 x 32 tile", 11, c["fg"], anchor="start")
    s.text(rx, y + 190, "the stage-wise form", 11.5, c["mute"])
    s.text(rx, y + 204, "writes 207.52 MB a frame", 11.5, c["mute"])
    s.text(rx, y + 218, "between its steps", 11.5, c["mute"])
    return dy + 28


def figure(theme):
    s = Svg(theme, "Tile-resident: the planes stay in the core's L1", FW)
    c = s.c
    s.text(
        16,
        22,
        "Tile-resident: a tile's planes never leave the core that took it",
        16,
        None,
        True,
    )
    s.text(
        16,
        40,
        "Sponza's overview, 1,920 x 1,080, lit, one P150A; MB are a frame's, "
        "over all cores",
        11.5,
        c["mute"],
    )
    bottom, _ = stagewise(s, 46)
    bottom = resident(s, bottom + 18)
    s.text(
        16,
        bottom + 22,
        "Stage-wise MB and ms: each command's (both layers' FILL and "
        "SHADE added); threads: the movers' bytes by path and pack's time in each step.",
        11.5,
        c["mute"],
    )
    return s.finish(bottom + 32)


def main():
    write({"resident": figure}, sys.argv[1] if len(sys.argv) > 1 else None)


if __name__ == "__main__":
    main()
