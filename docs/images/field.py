"""Draws docs/images/field-{light,dark}.svg: the field from the elements' light to a
pixel (a section with the voxels, one voxel gathering the elements it sees, a texel's
bits, a pixel's lookup), and the update as the job thread's kept graph beside the frames.

usage: python docs/images/field.py [output folder]    (the standard library only)

Names are those of src/prism_reference/indirect/field/ and
src/prism/stages/indirect/field_update/graph.py; the numbers are copied from
docs/internals/reference/indirect.md and measurements/gi_threads/README.md.
"""

import math
import sys

from draw import Svg, write

W = 830


def panel(s, y, h, title, colour, note=""):
    c = s.c
    s.rect(16, y, W - 32, h, c["box"], c["line"], layer=0)
    s.text(30, y + 22, title, 14, c[colour][0], True)
    if note:
        s.text(W - 30, y + 22, note, 12, c["mute"], anchor="end")


def circle(s, x, y, r, fill, stroke="none", sw=1.0, dash=None, layer=1):
    extra = f' stroke-dasharray="{dash}"' if dash else ""
    s.add(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{fill}" '
        f'stroke="{stroke}" stroke-width="{sw}"{extra}/>',
        layer,
    )


def section(s, top):
    """The section: floor and wall, the voxels, the elements, a gather and a lookup."""
    c = s.c
    h = 42  # a voxel's side on the page
    gx, gy, cols, rows = 56, top + 56, 8, 5
    floor = gy + rows * h - 14
    for i in range(cols + 1):
        s.rule(gx + i * h, gy, gx + i * h, floor, 0.6, "2 3")
    for j in range(rows):
        s.rule(gx, gy + j * h, gx + cols * h, gy + j * h, 0.6, "2 3")
    s.rect(gx - 6, floor, cols * h + 6, 7, c["dram"], c["rule"], rx=0, sw=0.6)
    s.rect(gx - 6, gy, 6, floor - gy, c["dram"], c["rule"], rx=0, sw=0.6)
    box_x, box_y = gx + 2 * h, floor - 34
    s.rect(box_x, box_y, 26, 34, c["dram"], c["rule"], rx=0, sw=0.8)
    elements = [(gx, gy + 18 + k * 32, 1, 0) for k in range(5)]
    for k in range(13):
        x = gx + 12 + k * 26
        if not box_x - 4 < x < box_x + 30:
            elements.append((x, floor, 0, -1))
    elements.append((box_x + 13, box_y, 0, -1))
    hidden = (box_x + 32, floor, 0, -1)
    elements.append(hidden)
    for x, y, nx, ny in elements:
        s.line(x, y, x + nx * 11, y + ny * 11, c["mute"], 1.0, head=False)
        circle(s, x, y, 3.2, c["a"][0])
    vx, vy = gx + 1.5 * h, gy + 3.5 * h
    s.rect(gx + h, gy + 3 * h, h, h, c["b"][2], c["b"][0], rx=0, sw=1.6, layer=0)
    circle(s, vx, vy, 2 * h, "none", c["b"][0], 1.2, "5 3", layer=0)
    for e in elements:
        if math.hypot(e[0] - vx, e[1] - vy) < 2 * h and e != hidden:
            s.line(vx, vy, e[0], e[1], "b", 0.9, head=False)
    s.line(vx, vy, hidden[0], hidden[1], c["p"][0], 1.2, dash="3 2", head=False)
    s.text(hidden[0] + 8, hidden[1] - 34, "hidden from", 11, c["p"][0])
    s.text(hidden[0] + 8, hidden[1] - 20, "the centre", 11, c["p"][0])
    for dx, dy in ((1, 0), (-1, 0), (0, -1), (0, 1)):
        s.line(vx, vy, vx + dx * 15, vy + dy * 15, "b", 1.6)
    s.text(vx, vy - 2 * h - 6, "R = 2h", 11, c["b"][0], True, anchor="middle")
    s.text(vx + h / 2 + 6, vy - h / 2 - 4, "a voxel", 11, c["b"][0], True)
    px, py = gx + 6.25 * h, floor
    qx, qy = px, py - h / 2
    i0, j0 = int((qx - gx) / h - 0.5), int((qy - gy) / h - 0.5)
    for di in (0, 1):
        for dj in (0, 1):
            cx, cy = gx + (i0 + di + 0.5) * h, gy + (j0 + dj + 0.5) * h
            s.line(qx, qy, cx, cy, "w", 1.0, head=False)
            circle(s, cx, cy, 3.6, c["w"][0])
    s.line(px, py, px, py - 34, "r", 1.6)
    circle(s, px, py, 4, c["r"][0])
    circle(s, qx, qy, 3, c["bg"], c["r"][0], 1.6)
    s.text(px + 8, py - 26, "n", 11, c["r"][0], True, mono=True)
    s.text(px, py + 22, "P", 12, c["r"][0], True, mono=True, anchor="middle")
    s.text(qx - 14, qy + 2, "Q", 12, c["r"][0], True, mono=True, anchor="end")
    s.text(
        gx + cols * h,
        gy - 8,
        "voxels of side h, the element spacing",
        11,
        c["mute"],
        anchor="end",
    )
    return gx + cols * h, floor + 24


def build_panel(s, top):
    c = s.c
    hgt = 352
    panel(
        s,
        top,
        hgt,
        "The field: voxels a pixel reads",
        "b",
        "Sponza: 72,367 voxels, h = 50.3",
    )
    right, _ = section(s, top)
    x = right + 26
    y = top + 56
    s.text(x, y, "a voxel, one of six directions d:", 12, c["fg"], True)
    s.text(x, y + 18, "sum w E / sum w over the elements within", 11.5, c["fg"])
    s.text(x, y + 34, "2h that its centre sees (one ray each),", 11.5, c["fg"])
    s.text(x, y + 50, "w = max(0, n.d) (1 - (r / 2h)^2)^2", 11.5, c["fg"], mono=True)
    s.text(x, y + 68, "E: the passes' sum plus the element's sky", 11, c["mute"])
    s.text(x, y + 83, "1.08 M weights; a direction with no element", 11, c["mute"])
    s.text(x, y + 98, "takes a neighbour's row (110,541 of them)", 11, c["mute"])
    # the texel
    ty = y + 126
    s.text(x, ty, "its texel, 32 bits (light.field's pages):", 12, c["fg"], True)
    bx, bw = x, W - 46 - x
    unit = bw / 32
    for start, bits, label, colour in (
        (0, 1, "has", "g"),
        (1, 11, "red 11", "a"),
        (12, 11, "green 11", "r"),
        (23, 9, "blue 9", "w"),
    ):
        edge, _, pale = c[colour]
        s.rect(bx + start * unit, ty + 10, bits * unit, 22, pale, edge, rx=1, sw=1)
        if bits > 1:
            s.text(
                bx + (start + bits / 2) * unit,
                ty + 25,
                label,
                11,
                c["fg"],
                anchor="middle",
            )
    s.text(
        bx, ty + 48, "codes: sqrt(v / scale) x (2^bits - 1)", 11, c["mute"], mono=True
    )
    # the lookup
    ly = ty + 76
    s.text(x, ly, "a pixel P with normal n (in LIGHT):", 12, c["fg"], True)
    s.text(x, ly + 18, "Q = P + n h / 2; the 8 voxel centres", 11.5, c["fg"])
    s.text(x, ly + 34, "around Q, trilinear (4 in this section);", 11.5, c["fg"])
    s.text(x, ly + 50, "on each axis the direction of n's sign,", 11.5, c["fg"])
    s.text(x, ly + 66, "the axes blended by n_a^2", 11.5, c["fg"])
    s.text(
        30,
        top + hgt - 12,
        "The elements' light (36,832 for Sponza) fills every voxel; "
        "LIGHT reads eight voxels a pixel.",
        11,
        c["mute"],
    )
    return top + hgt


def bars(s, y, items, colour, h=20):
    c = s.c
    for x0, x1, label in items:
        edge, _, pale = c[colour]
        s.rect(x0, y, x1 - x0, h, pale, edge, rx=3, sw=1)
        if label:
            s.text((x0 + x1) / 2, y + h / 2 + 4, label, 11, c["fg"], anchor="middle")


def update_panel(s, top):
    c = s.c
    hgt = 404
    panel(
        s,
        top,
        hgt,
        "The update beside the frames: a graph kept on the card",
        "m",
        "Sponza, gi_threads, 1,920 x 1,080",
    )
    lx, x0, x1 = 30, 190, W - 30
    rows = {
        "host": top + 50,
        "frame's thread": top + 86,
        "the ranks above": top + 122,
        "the lowest ranks": top + 158,
        "job thread": top + 194,
        "light pages": top + 232,
    }
    subs = {
        "frame's thread": "X280 cluster 1",
        "the ranks above": "the frames' threads",
        "the lowest ranks": "30 or more: the applies",
        "job thread": "X280 clusters 2, 3",
        "light pages": "the field, twice",
    }
    for name, y in rows.items():
        s.text(lx, y + 10, name, 12, c["fg"], True)
        if name in subs:
            s.text(lx, y + 24, subs[name], 11, c["mute"])
        s.rule(x0, y + 10, x1, y + 10, 0.5, "2 4")
    sun = x0 + 32
    s.line(sun, rows["host"] + 2, sun, rows["frame's thread"] - 2, "y", 1.6)
    s.text(sun + 6, rows["host"] + 6, "sun set", 11, c["y"][0], True)
    f, t = rows["frame's thread"], rows["the ranks above"]
    j, a = rows["job thread"], rows["the lowest ranks"]
    starts = (296, 420, 544)
    swap = 668
    bars(s, f, [(x0, x0 + 26, "")], "r")
    bars(s, f, [(sun + 4, sun + 70, "sun's pass")], "y")
    bars(s, f, [(x, x + 120, "old field") for x in starts], "r")
    bars(s, f, [(swap, swap + 60, "new field"), (swap + 64, x1, "")], "w")
    tiles = [(x0 + 2, x0 + 24, ""), (sun + 6, sun + 68, "")]
    tiles += [(x + 4, x + 116, "") for x in starts]
    tiles += [(swap + 4, swap + 56, ""), (swap + 68, x1 - 4, "")]
    bars(s, t, tiles, "g", 16)
    x = starts[0]
    for label, colour, w in (
        ("sources", "m", 64),
        ("apply", "a", 40),
        ("pass", "m", 56),
        ("apply", "a", 40),
        ("pass", "m", 56),
        ("finish", "m", 46),
        ("scale", "m", 40),
    ):
        if colour == "a":
            bars(s, a, [(x, x + w, label)], "a")
            s.line(x + 3, j + 4, x + 3, a + 22, "a", 1.0)
        else:
            bars(s, j, [(x, x + w, label)], "m")
        x += w + 3
    end = x - 3
    s.line(starts[0] + 2, j - 2, starts[0] + 2, f + 22, "p", 1.2)
    s.line(end - 2, j - 2, end - 2, f + 22, "p", 1.2)
    s.text(starts[0] + 6, j + 33, "job_wants: the cores", 11, c["p"][0], True)
    s.text(
        end + 2, j + 33, "job_wants: half B, scale", 11, c["p"][0], True, anchor="end"
    )
    lp = rows["light pages"]
    bars(s, lp, [(x0, swap - 2, "half A: read by LIGHT")], "b")
    bars(s, lp + 24, [(starts[0], end, "half B: written by the update")], "m", 18)
    bars(s, lp, [(swap, x1, "half B: read")], "w")
    s.line(swap - 1, f + 22, swap - 1, lp - 2, "w", 1.2, dash="3 2")
    s.line(x0, lp + 52, x1, lp + 52, "g", 1.0)
    s.text(x1, lp + 66, "time (schematic)", 11, c["mute"], anchor="end")
    g = top + 312
    s.text(lx, g + 10, "gi", 12, c["fg"], True, mono=True)
    s.text(lx, g + 24, "stage-wise", 11, c["mute"])
    bars(s, g, [(x0, x0 + 26, "")], "r")
    bars(
        s,
        g,
        [(sun + 4, x1 - 64, "sun's pass, then the update on every core: no frame")],
        "y",
    )
    bars(s, g, [(x1 - 60, x1, "")], "w")
    s.text(
        30,
        top + hgt - 44,
        "Sponza: gi_threads draws 3 frames during its update, 23.6 to "
        "23.7 ms each against 18.60 steady; its first",
        11.5,
        c["fg"],
    )
    s.text(
        30,
        top + hgt - 28,
        "frame with the new field ends 138.5 ms after the sun was set. "
        "gi stops 174.5 ms. Ten scenes: 2 to 7 frames,",
        11.5,
        c["fg"],
    )
    s.text(
        30,
        top + hgt - 12,
        "each 1.25 to 1.36 times the steady frame " "(measurements/gi_threads).",
        11.5,
        c["fg"],
    )
    return top + hgt


def field(theme):
    s = Svg(theme, "The indirect field and its update beside the frames", W)
    y = build_panel(s, 12)
    y = update_panel(s, y + 12)
    return s.finish(y + 12)


if __name__ == "__main__":
    write({"field": field}, sys.argv[1] if len(sys.argv) > 1 else None)
