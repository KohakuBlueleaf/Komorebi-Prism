"""Draws the README's first figure, docs/images/teaser-{light,dark}.svg: glTF in, frame
out. The host opens the file once and loads its tensors; each frame it sends one
command, FRAME, to the frame's thread on X280 cluster 1, whose pulls hand the frame's
tile threads to the 120 Tensix cores that ask; a core runs every step of the tile it
took and writes its display page; the host reads the pages back.

usage: python docs/images/teaser.py [output folder]    (the standard library only)

Names: prism_cli open, prism.loop (Loop.frame), the frame's thread
(prism.core.unit.FRAMES, cluster 1), the job thread (program/jobs/thread.py CLUSTERS 2
and 3), the tile thread LIT (program/threads/tiles.py), the grid of 32 x 32 tiles and
slices of 16 (docs/internals/program/dispatch.md). Numbers: measurements/gi_threads
(Sponza's overview, 1,920 x 1,080, gi_threads 18.610 ms, gi less its push 22.447 ms).
"""

import random
import sys

from draw import Svg, box, chip, write

FW = 880


def file_icon(s, x, y, w, h, name):
    c = s.c
    fold = 12
    d = (
        f"M{x},{y} L{x + w - fold},{y} L{x + w},{y + fold} L{x + w},{y + h} "
        f"L{x},{y + h} z"
    )
    s.add(f'<path d="{d}" fill="{c["box"]}" stroke="{c["rule"]}" stroke-width="1.3"/>')
    s.add(
        f'<path d="M{x + w - fold},{y} L{x + w - fold},{y + fold} L{x + w},{y + fold}" '
        f'fill="none" stroke="{c["rule"]}" stroke-width="1.3"/>'
    )
    s.text(x + w / 2, y + h / 2 + 4, name, 12, c["fg"], True, True, "middle")


def label(s, x, y, text, colour, anchor="middle", size=11.5, bold=True):
    s.text(x, y, text, size, s.c[colour][0], bold, anchor=anchor)


def teaser(theme):
    s = Svg(theme, "Komorebi-Prism: glTF in, frame out, the card drawing alone", FW)
    c = s.c
    s.text(
        16, 26, "glTF in, frame out: the card draws each frame alone", 17, None, True
    )
    s.text(
        16,
        45,
        "the host sends one command a frame; the cores take the frame's tiles "
        "one by one and run every step of the tile they took",
        12,
        c["mute"],
    )
    top, hgt = 60, 318

    # the host
    hx, hw = 16, 170
    box(s, hx, top, hw, hgt, "the host", "Python: prism.loop", "g")
    file_icon(s, hx + 40, top + 50, 90, 34, "scene.glb")
    s.line(hx + 40, top + 86, hx + 40, top + 108, "g", 1.6)
    s.text(hx + 48, top + 101, "prism_cli open", 11.5, c["fg"], mono=True)
    chip(s, hx + 14, top + 110, hw - 28, 40, "tables, once", "g", "loaded to DRAM once")
    s.text(hx + 14, top + 186, "each frame:", 12, c["mute"])
    s.text(hx + 14, top + 204, "Loop.frame(camera)", 11.5, c["fg"], True, True)
    s.text(hx + 14, top + 236, "sends camera + FRAME", 11.5, c["w"][0], True)
    s.text(hx + 14, top + 268, "after the frame:", 12, c["mute"])
    s.text(hx + 14, top + 286, "display pages read", 12, c["fg"])

    # the card
    cx, cw = 214, 370
    box(s, cx, top, cw, hgt, "one Blackhole P150A", "", "w")
    s.rect(cx + 12, top + 32, cw - 24, 34, c["dram"], rx=4)
    s.text(cx + 20, top + 47, "DRAM", 12, c["fg"], True)
    s.text(
        cx + 20,
        top + 61,
        "mesh blocks, lists, textures, shadow map, field",
        11,
        c["fg"],
    )
    # load arrow: host tables -> DRAM
    s.poly(
        [
            (hx + hw - 14, top + 122),
            (cx - 10, top + 122),
            (cx - 10, top + 49),
            (cx + 10, top + 49),
        ],
        "g",
        1.6,
    )

    # X280 cluster 1: the frame's thread
    xx, xy, xw, xh = cx + 12, top + 92, 110, 108
    s.rect(xx, xy, xw, xh, c["w"][2], c["w"][0], rx=6, sw=1.4)
    s.text(xx + 8, xy + 17, "X280 cluster 1", 11.5, c["w"][0], True)
    s.text(xx + 8, xy + 32, "the frame's", 12, c["fg"], True)
    s.text(xx + 8, xy + 46, "thread", 12, c["fg"], True)
    for i in range(4):
        s.rect(xx + 8 + i * 21, xy + 56, 17, 17, c["bg"], c["w"][0], rx=3, sw=1)
    s.text(xx + 8, xy + 88, "4 cores: a port", 11, c["mute"])
    s.text(xx + 8, xy + 101, "for 30 cores each", 11, c["mute"])
    # FRAME arrow: host -> X280 1
    s.line(hx + hw - 14, top + 214, xx - 2, xy + 62, "w", 2.2)
    # X280 2, 3: the job thread
    jx, jy, jh = xx, xy + xh + 14, 92
    s.rect(jx, jy, xw, jh, c["m"][2], c["m"][0], rx=6, sw=1.4)
    s.text(jx + 8, jy + 17, "X280 clusters 2, 3", 11, c["m"][0], True)
    s.text(jx + 8, jy + 33, "the job thread", 12, c["fg"], True)
    s.text(jx + 8, jy + 50, "the indirect", 11, c["mute"])
    s.text(jx + 8, jy + 64, "field's update,", 11, c["mute"])
    s.text(jx + 8, jy + 78, "beside the frames", 11, c["mute"])
    # display pages back: DRAM -> host
    s.line(cx + 2, top + 282, hx + hw - 14, top + 282, "r", 1.6, dash="5 3")

    # the 120 Tensix cores
    gx, gy, cell, gap = cx + 136, top + 92, 15, 3
    rng = random.Random(3)
    busy = {}
    for i in range(120):
        r, k = divmod(i, 12)
        x = gx + k * (cell + gap) + (6 if k >= 6 else 0)
        y = gy + r * (cell + gap)
        on = rng.random() < 0.85
        busy[i] = (x, y)
        fill = c["r"][1] if on else c["cell"]
        s.rect(x, y, cell, cell, fill, c["r"][0] if on else c["line"], rx=2, sw=0.8)
    s.text(
        gx, gy + 10 * (cell + gap) + 12, "120 Tensix cores, each asking", 11.5, c["fg"]
    )
    s.text(gx, gy + 10 * (cell + gap) + 26, "for its next tile thread", 11.5, c["fg"])
    # pulls: X280 1 <-> a few cores
    for core in (13, 40, 66, 99):
        x, y = busy[core]
        s.line(xx + xw + 2, xy + 64, x - 1, y + cell / 2, "w", 1.1, tail=True)
    label(s, xx + xw + 6, xy - 6, "pulls: ask, answer", "w", "start", 11.5)

    # the frame
    fx, fw = 600, FW - 600 - 16
    box(s, fx, top, fw, hgt, "the frame", "1,920 x 1,080: 60 x 34 tiles", "r")
    tx, ty, t = fx + 14, top + 52, 4
    rng = random.Random(11)
    order = list(range(60 * 34))
    runs = []  # (row, first, last, fill): a row's tiles of one fill as one rect
    for tile in order:
        r, k = divmod(tile, 60)
        slice_ = r * 4 + k // 16
        if r < 22 or (r < 26 and (slice_ * 5) % 7 < 3):
            fill = c["r"][1]
        elif r < 26 and rng.random() < 0.25:
            fill = c["r"][0]
        else:
            fill = c["cell"]
        if runs and runs[-1][0] == r and runs[-1][3] == fill:
            runs[-1][2] = k
        else:
            runs.append([r, k, k, fill])
    for r, a, b, fill in runs:
        s.rect(tx + a * t, ty + r * t, (b - a + 1) * t, t, fill, rx=0)
    grid = "".join(f"M{tx + k * t:.1f},{ty} v{34 * t}" for k in range(61))
    grid += "".join(f"M{tx},{ty + r * t:.1f} h{60 * t}" for r in range(35))
    s.add(f'<path d="{grid}" stroke="{c["bg"]}" stroke-width="0.6" fill="none"/>')
    # one slice outlined: row 24, tiles 16..31
    sr = 24
    s.rect(
        tx + 16 * t - 1,
        ty + sr * t - 1,
        16 * t + 1,
        t + 1.4,
        "none",
        c["a"][0],
        rx=1,
        sw=1.4,
    )
    gh = 34 * t
    s.text(tx, ty + gh + 16, "a slice: 16 tiles of a row", 11.5, c["a"][0], True)
    # the core -> its tile
    core_x, core_y = busy[40]
    hot_x, hot_y = tx + 22 * t, ty + sr * t + 2
    s.rect(hot_x - 1.5, hot_y - 3.5, t + 3, t + 3, c["r"][0], rx=1)
    s.add(
        f'<rect x="{core_x - 2:.1f}" y="{core_y - 2:.1f}" width="{cell + 4}" '
        f'height="{cell + 4}" rx="3" fill="none" stroke="{c["fg"]}" stroke-width="1.6"/>',
        2,
    )
    s.poly(
        [
            (core_x + cell + 2, core_y + cell / 2),
            (fx - 6, core_y + cell / 2),
            (hot_x, hot_y),
        ],
        "r",
        1.6,
    )
    # the steps of a tile thread
    sy = ty + gh + 30
    s.text(tx, sy, "the core that took a tile runs:", 11.5, c["fg"])
    steps = ("visibility", "material_lit", "light", "post")
    widths = (74, 92, 46, 40)
    x = tx
    for name, w in zip(steps, widths, strict=True):
        chip(s, x, sy + 8, w, 22, name, "r", size=11)
        x += w + 4
    s.rect(tx, sy + 36, fw - 28, 18, c["y"][2], c["y"][0], rx=4, sw=1)
    s.text(tx + 6, sy + 49, "the tile's planes stay in its L1", 11.5, c["fg"])
    s.text(tx, sy + 72, "then writes one display page", 11.5, c["fg"])
    s.text(tx, sy + 87, "(32 x 32 pixels) to DRAM", 11.5, c["fg"])

    # legend line and the numbers
    ly = top + hgt + 22
    items = (
        (c["r"][1], c["r"][0], "a core with a tile thread; a tile written"),
        (c["r"][0], c["r"][0], "a tile being drawn"),
        (c["cell"], c["line"], "idle core; tile not yet taken"),
    )
    x = 16
    for fill, edge, text in items:
        s.rect(x, ly - 10, 12, 12, fill, edge, rx=2, sw=0.8)
        s.text(x + 18, ly, text, 11.5, c["fg"])
        x += 30 + 6.3 * len(text)
    ny = ly + 26
    s.text(16, ny + 4, "Sponza, 1,920 x 1,080, ms a frame", 12, c["fg"], True)
    scale = 330 / 22.447
    bars = (
        ("gi_threads", 18.610, "r", "threads"),
        ("gi less push", 22.447, "g", "stage-wise"),
    )
    for i, (name, ms, colour, note) in enumerate(bars):
        y = ny + 16 + i * 24
        s.text(320, y + 12, name, 11.5, c["fg"], True, True, "end")
        s.rect(330, y, ms * scale, 17, c[colour][1], c[colour][0], rx=3, sw=1)
        s.text(336 + ms * scale, y + 13, f"{ms:.3f}  {note}", 11.5, c["fg"])
    return s.finish(ny + 70)


def main():
    write({"teaser": teaser}, sys.argv[1] if len(sys.argv) > 1 else None)


if __name__ == "__main__":
    main()
