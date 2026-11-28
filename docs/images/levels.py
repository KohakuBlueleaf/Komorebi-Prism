"""Draws docs/images/levels-{light,dark}.svg: the renderer at three levels, each zoomed
from the one above: the machine (the host, PCIe, the card's DRAM banks, X280 clusters
and 120 Tensix cores by their ports), a frame (the view's phases on the frame's thread:
what each hands out, what the cores do with it, what it leaves in DRAM), one core (its
five CPUs, the rings between them, what its L1 holds through a tile thread).

usage: python docs/images/levels.py [output folder]    (the standard library only)

Names: program/threads/program.py (ports: core * 4 // cores on cluster 1), the job
thread's clusters 2 and 3 (program/jobs/thread.py), an update's applies as core steps
on every rank (stages/indirect/field_update/graph.py), the phases of program/dispatch/c/dispatch_view.c and
docs/internals/program/dispatch.md, the handler work's CPUs, rings and memory
(docs/internals/program/work.md), the tile thread LIT (program/threads/tiles.py).
"""

import sys

from draw import Svg, box, chip, write

FW = 880
PORTS = ("a", "b", "r", "p")  # the colours of X280 1's four cores' ports


def lines(s, x, y, text, size=11.5, fill=None, step=14, mono=False, bold=False):
    """Each line of `text` (split on |) one under the other; returns the y after."""
    for line in text.split("|"):
        s.text(x, y, line, size, fill, bold, mono)
        y += step
    return y


def zoom(s, x1a, x1b, y1, x2a, x2b, y2):
    """A pale wedge from the span x1a..x1b at y1 to x2a..x2b at y2."""
    c = s.c
    d = f"M{x1a},{y1} L{x1b},{y1} L{x2b},{y2} L{x2a},{y2} z"
    s.add(f'<path d="{d}" fill="{c["cell"]}" opacity="0.7" stroke="none"/>', 0)
    s.rule(x1a, y1, x2a, y2, 1, "3 3")
    s.rule(x1b, y1, x2b, y2, 1, "3 3")


def machine(s, top):
    """Level 1; returns (bottom, the X280 1 box's x span, the core 40's box)."""
    c = s.c
    s.text(16, top + 16, "1  the machine", 14, c["fg"], True)
    s.text(150, top + 16, "what holds what, and who talks to whom", 12, c["mute"])
    y0 = top + 30
    # the host
    box(s, 16, y0, 112, 220, "the host", "x86-64, Python", "g")
    lines(
        s,
        28,
        y0 + 64,
        "opens the scene|loads tensors|writes the camera|sends FRAME|"
        "reads the display|pages",
        11.5,
        c["fg"],
    )
    # the card
    kx, kw = 168, FW - 16 - 168
    box(s, kx, y0, kw, 248, "the card: one Blackhole P150A", "", "w")
    s.line(130, y0 + 110, kx - 2, y0 + 110, "g", 2.0, tail=True)
    s.text(149, y0 + 102, "PCIe", 11.5, c["mute"], True, anchor="middle")
    cell, gap = 15, 3
    pitch = cell + gap
    gy = y0 + 36
    dl, tl = kx + 12, kx + 40  # left DRAM column, left Tensix block
    xc = tl + 6 * pitch + 8  # the X280 column
    dr = xc + 90  # right DRAM column
    tr = dr + 28  # right Tensix block
    core_box = {}
    for row in range(10):
        y = gy + row * pitch * 1.1
        for i, dx in enumerate((dl, dr)):
            s.rect(dx, y, 22, cell, c["dram"], rx=2)
            s.text(dx + 11, y + 11, f"D{row % 4 + 4 * i}", 11, c["fg"], anchor="middle")
        for k in range(12):
            rank = row * 12 + k
            x = (tl if k < 6 else tr) + (k % 6) * pitch
            colour = PORTS[rank * 4 // 120]
            s.rect(x, y, cell, cell, c[colour][1], c[colour][0], rx=2, sw=0.6)
            core_box[rank] = (x, y)
    # the X280 clusters
    names = (
        ("X280 0", "g", "Komorebi"),
        ("X280 1", "w", "frame's thread"),
        ("X280 2", "m", "job thread"),
        ("X280 3", "m", "job thread"),
    )
    x280 = {}
    for i, (name, colour, sub) in enumerate(names):
        y = gy + i * 46
        s.rect(xc, y, 78, 40, c[colour][2], c[colour][0], rx=4, sw=1.4)
        s.text(xc + 39, y + 13, name, 11, c[colour][0], True, anchor="middle")
        lines(s, xc + 6, y + 26, sub, 11, c["fg"], 12)
        x280[i] = (xc, y)
    # the legend inside the card, right part
    lx = tr + 6 * pitch + 14
    ly = gy + 6
    s.text(lx, ly, "120 Tensix cores", 12, c["fg"], True)
    ly = lines(s, lx, ly + 16, "each asks one core of|X280 1, its port:", 11.5, c["fg"])
    for i, colour in enumerate(PORTS):
        s.rect(lx, ly - 9 + i * 17, 12, 12, c[colour][1], c[colour][0], rx=2, sw=0.6)
        s.text(
            lx + 18, ly + 1 + i * 17, f"ranks {30 * i} to {30 * i + 29}", 11.5, c["fg"]
        )
    ly += 4 * 17 + 8
    lines(
        s,
        lx,
        ly + 1,
        "an update's applies: every|rank, between two frames",
        11.5,
        c["fg"],
    )
    ly += 36
    lines(
        s,
        lx,
        ly,
        "D0 to D7: the DRAM banks: the scene,|the lists, a frame's pages. X280 0 is|Komorebi's; 1 to 3 run the renderer's threads",
        11.5,
        c["mute"],
    )
    xs = (x280[1][0], x280[1][0] + 78)
    return y0 + 248, xs, y0 + 248, core_box[40]


PHASES = (
    (
        "count",
        "pull",
        "w",
        "a pull: ranges of|blocks to whoever|asks; who took each",
        "count: each box|into the tiles it|reaches",
        "counts and rows|pages, a core",
    ),
    (
        "sums",
        "command",
        "g",
        "an ordinary|command on|every core",
        "slice s on rank|s mod cores: its|records by weight",
        "records, the|slices' words",
    ),
    (
        "running sum",
        "X280",
        "w",
        "each layer's place|a slice; entries|against list slots",
        "(waiting)",
        "the slices'|places",
    ),
    (
        "place",
        "pull",
        "w",
        "a pull replaying|the log: each core|its own ranges",
        "place: set-up;|each record into|its tiles' lists",
        "each layer's|lists",
    ),
    (
        "words",
        "X280",
        "w",
        "each step's|words of the|frame's page",
        "(waiting)",
        "the frame's|page",
    ),
    (
        "tile",
        "pull",
        "r",
        "a pull: dp_choose|picks the next|record (prefer)",
        "a tile thread:|every step of|one tile",
        "display pages,|one a tile",
    ),
)


def frame(s, top, xs, xbottom):
    """Level 2; returns (bottom, the tile column's x span)."""
    c = s.c
    zoom(s, xs[0], xs[1], xbottom, 16, FW - 16, top + 6)
    s.rect(16, top + 6, FW - 32, 286, c["bg"], c["w"][0], rx=6, sw=1.2, layer=0)
    s.text(28, top + 28, "2  a frame", 14, c["fg"], True)
    s.text(
        124,
        top + 28,
        "one view on the frame's thread: four pulls, one command, "
        "two steps on the X280",
        12,
        c["mute"],
    )
    rows = (
        ("X280 1", "w", top + 46),
        ("Tensix", "r", top + 120),
        ("DRAM", "g", top + 200),
    )
    for name, colour, y in rows:
        s.text(28, y + 22, name, 12, c[colour][0], True)
    s.text(28, rows[1][2] + 38, "cores", 12, c["r"][0], True)
    s.text(28, rows[2][2] + 38, "leaves", 12, c["mute"])
    x0, cw = 92, 128
    tile_span = None
    for i, (name, how, colour, hands, does, leaves) in enumerate(PHASES):
        x = x0 + i * cw
        on_cores = does != "(waiting)"
        s.text(x + 4, top + 44, f"{i + 1} {name}", 12, c["fg"], True)
        s.rect(x, top + 50, cw - 8, 58, c["w"][2], c["w"][0], rx=4, sw=1)
        lines(s, x + 6, top + 66, hands, 11, c["fg"], 14)
        if on_cores:
            s.rect(
                x,
                top + 124,
                cw - 8,
                58,
                c[colour][2] if colour != "g" else c["box"],
                c[colour][0],
                rx=4,
                sw=1,
            )
            lines(s, x + 6, top + 140, does, 11, c["fg"], 14)
            s.line(x + cw / 2 - 4, top + 109, x + cw / 2 - 4, top + 122, "w", 1.4)
            s.line(x + cw / 2 - 4, top + 183, x + cw / 2 - 4, top + 202, "g", 1.4)
        else:
            s.rect(x, top + 124, cw - 8, 58, "none", c["line"], rx=4, sw=1, dash="4 3")
            s.text(
                x + (cw - 8) / 2,
                top + 157,
                "cores wait",
                11,
                c["mute"],
                anchor="middle",
            )
            s.poly(
                [(x + cw - 14, top + 108), (x + cw - 14, top + 202)],
                "g",
                1.2,
                dash="3 3",
            )
        s.rect(x, top + 204, cw - 8, 36, c["dram"], rx=4)
        lines(s, x + 6, top + 218, leaves, 11, c["fg"], 13)
        if i < len(PHASES) - 1:
            s.line(x + cw - 7, top + 79, x + cw - 1, top + 79, "w", 1.4)
        if name == "tile":
            tile_span = (x, x + cw - 8)
    s.text(
        x0,
        top + 262,
        "a frame of 1,920 x 1,080: 60 x 34 tiles, 136 slices of 16 "
        "tiles, 2,040 tile threads; a range is 4 blocks of 32 triangles on Sponza",
        11.5,
        c["fg"],
    )
    s.text(
        x0,
        top + 279,
        "ranges outside the view are skipped; a standing camera runs the tile pull "
        "alone; the sums and running sum wait for every core",
        11.5,
        c["mute"],
    )
    return top + 292, tile_span


def core(s, top, span):
    """Level 3; returns its bottom."""
    c = s.c
    zoom(s, span[0], span[1], top - 40, 16, FW - 16, top + 6)
    y0 = top + 6
    s.rect(16, y0, FW - 32, 300, c["bg"], c["r"][0], rx=6, sw=1.2, layer=0)
    s.text(28, y0 + 22, "3  one core", 14, c["fg"], True)
    s.text(
        124,
        y0 + 22,
        "a Tensix core running a tile thread: five CPUs, one L1, "
        "nothing of the tile written but its display page",
        12,
        c["mute"],
    )
    # the port and DRAM, outside the core's box
    px = 32
    s.rect(px, y0 + 44, 110, 44, c["w"][2], c["w"][0], rx=4, sw=1.2)
    lines(s, px + 8, y0 + 61, "its port on|X280 1", 11.5, c["fg"], 14, bold=True)
    s.rect(px, y0 + 120, 110, 120, c["dram"], rx=4)
    lines(
        s,
        px + 8,
        y0 + 138,
        "DRAM|the record|the lists|texture pages|light pages|" "the display page",
        11.5,
        c["fg"],
        16,
    )
    # the core
    cx, cy, cw, ch = 176, y0 + 38, FW - 32 - 176, 252
    s.rect(cx, cy, cw, ch, c["box"], c["r"][0], rx=6, sw=1.4, layer=0)
    # movers
    ma = (cx + 12, cy + 12, 150, 58)
    mb = (cx + 12, cy + 84, 150, 50)
    for (x, y, w, h), name, text in (
        (ma, "mover A", "asks; reads the record;|hands on the descriptor"),
        (mb, "mover B", "follows mover A"),
    ):
        s.rect(x, y, w, h, c["w"][2], c["w"][0], rx=4, sw=1.2)
        s.text(x + 8, y + 16, name, 12, c["fg"], True)
        lines(s, x + 8, y + 31, text, 11, c["fg"], 13)
    s.line(px + 112, y0 + 66, ma[0] - 2, ma[1] + 20, "w", 1.6, tail=True)
    s.text(px, y0 + 104, "ask / answer", 11, c["w"][0], True)
    s.line(px + 112, y0 + 160, mb[0] - 2, mb[1] + 30, "g", 1.6)
    s.line(px + 112, y0 + 150, ma[0] - 2, ma[1] + 50, "g", 1.6)
    s.text(px + 118, y0 + 210, "read", 11, c["mute"], True)
    # compute CPUs and the steps
    kx = cx + 250
    s.rect(kx, cy + 12, cw - 262, 130, c["r"][2], c["r"][0], rx=4, sw=1.2)
    s.text(kx + 8, cy + 28, "unpack, math, pack: the steps in order", 12, c["fg"], True)
    steps = ("visibility", "material_lit", "light", "post")
    sw = (cw - 262 - 16 - 3 * 14) / 4
    for i, name in enumerate(steps):
        x = kx + 8 + i * (sw + 14)
        chip(s, x, cy + 40, sw, 26, name, "r", size=11.5)
        if i:
            s.line(x - 13, cy + 53, x - 1, cy + 53, "r", 1.4)
    lines(
        s,
        kx + 8,
        cy + 86,
        "pack asks the movers for pages (frame_asks_a, _b);|"
        "post's output blocks go to a mover, which converts|and writes them",
        11,
        c["fg"],
        14,
    )
    # rings between
    for y, text in ((cy + 30, "frame_jobs"), (cy + 96, "frame_list_a|frame_list_b")):
        s.line(ma[0] + 152, y + 8, kx - 2, y + 8, "w", 1.4)
        lines(s, ma[0] + 156, y + 2, text, 11, c["fg"], 26, mono=True)
    # out: display page
    s.poly([(kx + 30, cy + 142), (kx + 30, cy + 152), (px + 112, cy + 152)], "r", 1.6)
    s.text(cx + 12, cy + 148, "the display page: the one write", 11, c["r"][0], True)
    # L1
    ly = cy + 176
    s.text(
        cx + 12,
        ly + 4,
        "L1, the handler work's memory, held through the tile thread",
        12,
        c["fg"],
        True,
    )
    parts = (
        ("shared line", 1216, "g", "1,216 B"),
        ("steps' kept state", 2800, "a", "page cache, light table"),
        ("frame.visibility", 81920 // 20, "y", "20 x 4 KiB"),
        ("frame.surface", 81920 // 20, "y", "20 x 4 KiB"),
    )
    x, bw = cx + 12, cw - 24
    shares = (0.15, 0.27, 0.29, 0.29)
    for (name, _, colour, sub), share in zip(parts, shares, strict=True):
        w = bw * share
        s.rect(x, ly + 12, w - 3, 48, c[colour][2], c[colour][0], rx=3, sw=1)
        s.text(x + 6, ly + 30, name, 11.5, c["fg"], True, mono=name.startswith("frame"))
        s.text(x + 6, ly + 47, sub, 11, c["mute"])
        x += w
    return y0 + 300


def levels(theme):
    s = Svg(theme, "Komorebi-Prism at three levels: machine, frame, core", FW)
    bottom, xs, xb, _ = machine(s, 0)
    bottom, span = frame(s, bottom + 40, xs, xb)
    bottom = core(s, bottom + 40, span)
    return s.finish(bottom + 12)


def main():
    write({"levels": levels}, sys.argv[1] if len(sys.argv) > 1 else None)


if __name__ == "__main__":
    main()
