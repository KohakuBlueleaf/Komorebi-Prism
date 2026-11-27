"""Draws docs/images/transport-{light,dark}.svg: the indirect light as one matrix product
y = M x, Sponza's matrix as it is stored (dense near blocks, low-rank far blocks, zero
blocks dropped), a block as 32 x 32 tiles, the apply as one command on every core (the
receivers dealt in ranges, a core's movers and matrix engine), and the bounce passes.

usage: python docs/images/transport.py [output folder]    (the standard library only)

The map is Sponza's transport set (blocks.npz) drawn on 128 x 128 cells, each cell the
class holding most of its tiles; the ranges are plan/deal.py's for Sponza on 120 cores.
Names are those of src/prism/stages/indirect/transport/; the numbers are copied from
docs/internals/reference/indirect.md and measurements/apply/README.md.
"""

import base64
import struct
import sys
import zlib

from draw import Svg, chip, write

W = 830
CELLS = 128
TILES = 1151
# Sponza's receiver tiles dealt to 120 cores: each core's first tile, then the end.
FIRST = (
    0, 12, 21, 31, 38, 47, 53, 63, 71, 87, 96, 106, 115, 125, 134, 145, 157, 166, 176,
    183, 192, 201, 210, 222, 232, 243, 251, 260, 271, 279, 287, 296, 303, 310, 318, 326,
    337, 347, 356, 363, 372, 381, 391, 404, 416, 427, 435, 445, 453, 463, 473, 485, 498,
    505, 514, 523, 532, 541, 553, 562, 575, 588, 597, 608, 616, 625, 634, 643, 655, 664,
    675, 683, 692, 703, 713, 722, 732, 741, 752, 760, 769, 776, 784, 791, 800, 812, 827,
    836, 847, 858, 867, 877, 885, 896, 907, 917, 928, 937, 946, 955, 965, 974, 987, 996,
    1007, 1017, 1025, 1034, 1041, 1048, 1057, 1067, 1078, 1083, 1093, 1102, 1114, 1123,
    1133, 1148, 1151,
)  # fmt: skip
SPONZA = (
    "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"
    "A1hrOfE="
)


def cells():
    """The map's classes, row by row: 0 dropped, 1 low rank, 2 dense."""
    return zlib.decompress(base64.b64decode("".join(SPONZA)))


def png(rows, palette):
    """A palette PNG of `rows` (lists of indices) as a data URI."""

    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    h, w = len(rows), len(rows[0])
    raw = b"".join(b"\x00" + bytes(row) for row in rows)
    plte = b"".join(bytes.fromhex(colour[1:]) for colour in palette)
    data = b"\x89PNG\r\n\x1a\n" + chunk(
        b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 3, 0, 0, 0)
    )
    data += chunk(b"PLTE", plte) + chunk(b"IDAT", zlib.compress(raw, 9))
    data += chunk(b"IEND", b"")
    return "data:image/png;base64," + base64.b64encode(data).decode()


def panel(s, y, h, title, colour, note=""):
    c = s.c
    s.rect(16, y, W - 32, h, c["box"], c["line"], layer=0)
    s.text(30, y + 22, title, 14, c[colour][0], True)
    if note:
        s.text(W - 30, y + 22, note, 12, c["mute"], anchor="end")


def tile(s, x, y, size, colour, rgb=False):
    """A 32 x 32 tile; `rgb`: x's tile, its first three rows the colours."""
    edge, mid, pale = s.c[colour]
    s.rect(x, y, size, size, pale, edge, rx=1, sw=0.8)
    if rgb:
        s.rect(x + 1, y + 1, size - 2, max(2.0, size * 3 / 32), mid, "none", rx=0)


def grid(s, x, y, rows, cols, size, colour, gap=1.5):
    for i in range(rows):
        for j in range(cols):
            tile(s, x + j * (size + gap), y + i * (size + gap), size, colour)
    return cols * (size + gap) - gap, rows * (size + gap) - gap


def bar(s, x, y, w, h, colour, ticks, vertical=False):
    """A strip of `ticks` tiles drawn as one bar with tile marks."""
    edge, _, pale = s.c[colour]
    s.rect(x, y, w, h, pale, edge, rx=1, sw=0.8)
    for k in range(1, ticks):
        if vertical:
            s.rule(x, y + h * k / ticks, x + w, y + h * k / ticks, 0.5)
        else:
            s.rule(x + w * k / ticks, y, x + w * k / ticks, y + h, 0.5)


def matrix_panel(s, top):
    c = s.c
    panel(
        s,
        top,
        474,
        "y = M x: what each element receives from every other",
        "a",
        "Sponza, 36,832 elements",
    )
    s.text(
        30, top + 44, "M as stored: rows the receivers (y), columns the sources (x)", 12
    )
    s.text(
        30,
        top + 60,
        "1,151 x 1,151 tiles of 32 x 32, cut by the elements' cluster tree",
        11.5,
        c["mute"],
    )
    mx, my, side = 34, top + 74, 300
    data = cells()
    palette = (c["cell"], c["b"][1], c["a"][0])
    rows = [list(data[i * CELLS : (i + 1) * CELLS]) for i in range(CELLS)]
    big = [[v for v in row for _ in range(3)] for row in rows for _ in range(3)]
    s.add(
        f'<image x="{mx}" y="{my}" width="{side}" height="{side}" '
        f'href="{png(big, palette)}" preserveAspectRatio="none"/>'
    )
    s.rect(mx, my, side, side, "none", c["rule"], rx=0, sw=1)
    k = side / TILES
    # the legend under the map
    ly = my + side + 18
    for i, (fill, label, sub) in enumerate(
        (
            (c["a"][0], "dense near block", "13,024 blocks, 265,798 tiles"),
            (c["b"][1], "low-rank block U V^T", "8,406 blocks, 155,628 tiles"),
            (c["cell"], "zero block, dropped", "no tiles"),
        )
    ):
        x, yy = mx + 160 * (i % 2), ly + 36 * (i // 2)
        s.rect(x, yy - 10, 12, 12, fill, c["rule"], rx=2, sw=0.6)
        s.text(x + 18, yy, label, 11.5, c["fg"], True)
        s.text(x + 18, yy + 15, sub, 11, c["mute"])
    s.text(mx + 178, ly + 36, "421,426 tiles in all,", 11, c["mute"])
    s.text(mx + 178, ly + 51, "bfp8_b: 1,088 B a tile", 11, c["mute"])
    # the three blocks picked
    picks = (
        (147, 147, 5, 5, "a", "1"),
        (395, 71, 9, 9, "b", "2"),
        (719, 287, 72, 72, "b", "3"),
    )
    marks = []
    for r0, c0, m, n, colour, name in picks:
        bx, by = mx + c0 * k, my + r0 * k
        bw, bh = max(m * k, 7), max(n * k, 7)
        bx -= (bw - n * k) / 2
        by -= (bh - m * k) / 2
        s.rect(bx, by, bw, bh, "none", c["fg"], rx=1, sw=1.6, layer=2)
        s.text(bx + bw / 2, by - 4, name, 11, c["fg"], True, anchor="middle")
        marks.append((bx + bw, by + bh / 2))
    # zoom 1: the dense block
    zx, zy = 388, top + 50
    t = 15
    s.text(
        zx,
        zy + 10,
        "1  a dense near block, receivers 147-151 by sources 147-151",
        12,
        c["fg"],
        True,
    )
    s.text(
        zx, zy + 26, "W^T stored as 5 x 5 tiles: 25 tile products a pass", 11, c["mute"]
    )
    gx, gy = zx + 40, zy + 62
    for j in range(5):
        tile(s, gx + j * (t + 2), gy - t - 8, t, "w", rgb=True)
    gw, gh = grid(s, gx, gy, 5, 5, t, "a", 2)
    s.text(gx - 6, gy - 13, "x", 12, c["w"][0], True, anchor="end", mono=True)
    s.text(gx - 6, gy + gh / 2 + 4, "W^T", 11, c["a"][0], True, anchor="end", mono=True)
    for i in range(5):
        tile(s, gx + gw + 30, gy + i * (t + 2), t, "r")
    s.line(gx + gw + 6, gy + gh / 2, gx + gw + 26, gy + gh / 2, "r", 1.6)
    s.text(gx + gw + 30 + t + 6, gy + gh / 2 + 4, "y", 12, c["r"][0], True, mono=True)
    s.text(gx + gw + 70, gy + 8, "x: a row of tiles,", 11, c["mute"])
    s.text(gx + gw + 70, gy + 23, "its rows 0-2 the colours", 11, c["mute"])
    s.text(gx + gw + 70, gy + 38, "R, G, B (bfloat16)", 11, c["mute"])
    s.text(gx + gw + 70, gy + 60, "y: float32 sums", 11, c["mute"])
    s.poly(
        [marks[0], (zx - 8, marks[0][1]), (zx - 8, zy + 6), (zx - 2, zy + 6)], "a", 1.2
    )
    # zoom 2: a 9 x 9 low-rank block
    zy2 = top + 206
    s.text(
        zx,
        zy2 + 10,
        "2  a low-rank block, 9 x 9 tiles, rank 19 (padded to one tile)",
        12,
        c["fg"],
        True,
    )
    s.text(
        zx,
        zy2 + 26,
        "t = V^T x, then y += U t: 18 tile products, not 81",
        11,
        c["mute"],
    )
    t2 = 12
    vx, vy = zx + 40, zy2 + 44
    for j in range(9):
        tile(s, vx + j * (t2 + 1.5), vy, t2, "w", rgb=True)
    s.text(vx - 6, vy + 10, "x", 12, c["w"][0], True, anchor="end", mono=True)
    bar(s, vx, vy + t2 + 6, 9 * (t2 + 1.5) - 1.5, t2, "b", 9)
    s.text(vx - 6, vy + t2 + 16, "V^T", 11, c["b"][0], True, anchor="end", mono=True)
    tx = vx + 9 * (t2 + 1.5) + 22
    s.line(tx - 18, vy + t2 + 12, tx - 4, vy + t2 + 12, "m", 1.4)
    tile(s, tx, vy + t2 + 6, t2, "m")
    s.text(tx + t2 + 5, vy + t2 + 16, "t", 12, c["m"][0], True, mono=True)
    ux = tx + 40
    bar(s, ux, vy + t2 + 6, 9 * (t2 + 1.5) - 1.5, t2, "b", 9)
    s.text(
        ux + 9 * (t2 + 1.5) / 2,
        vy + 10,
        "U^T: one tile by 9",
        11,
        c["b"][0],
        True,
        anchor="middle",
    )
    s.line(
        ux + 9 * (t2 + 1.5) + 4,
        vy + t2 + 12,
        ux + 9 * (t2 + 1.5) + 18,
        vy + t2 + 12,
        "r",
        1.4,
    )
    s.text(ux + 9 * (t2 + 1.5) + 22, vy + t2 + 16, "y", 12, c["r"][0], True, mono=True)
    s.poly(
        [marks[1], (zx - 14, marks[1][1]), (zx - 14, zy2 + 6), (zx - 2, zy2 + 6)],
        "b",
        1.2,
    )
    # zoom 3: a 72 x 72 low-rank block
    zy3 = top + 304
    s.text(
        zx,
        zy3 + 10,
        "3  a far block, 72 x 72 tiles, rank 94 (padded to 3 tiles)",
        12,
        c["fg"],
        True,
    )
    s.text(
        zx,
        zy3 + 26,
        "dense it would be 5,184 tiles; as V and U^T it is 432",
        11,
        c["mute"],
    )
    by3 = zy3 + 40
    s.rect(zx + 40, by3, 72, 72, "none", c["rule"], rx=0, sw=0.8, dash="3 2")
    s.text(zx + 76, by3 + 40, "72 x 72", 11, c["mute"], anchor="middle")
    bar(s, zx + 130, by3, 3, 72, "b", 1)
    s.text(zx + 140, by3 + 40, "V: 72 x 3", 11, c["b"][0], True)
    bar(s, zx + 210, by3 + 34, 72, 3, "b", 1)
    s.text(zx + 210, by3 + 28, "U^T: 3 x 72", 11, c["b"][0], True)
    s.text(zx + 300, by3 + 30, "median rank of", 11, c["mute"])
    s.text(zx + 300, by3 + 45, "a low-rank block: 14", 11, c["mute"])
    s.poly(
        [marks[2], (zx - 20, marks[2][1]), (zx - 20, zy3 + 6), (zx - 2, zy3 + 6)],
        "b",
        1.2,
    )
    s.text(
        30,
        top + 462,
        "A block of two far boxes (their gap at least the larger diagonal) is "
        "low rank when its rank at 1e-2 stores fewer numbers.",
        11,
        c["mute"],
    )
    return top + 474


def apply_panel(s, top):
    c = s.c
    h = 390
    panel(
        s,
        top,
        h,
        "The apply: one command, every core, tile products on the matrix engines",
        "w",
    )
    s.text(
        30,
        top + 44,
        "y's 1,151 receiver tiles dealt in contiguous ranges, one a core "
        "(plan/deal.py): 3 to 16 tiles each, each about 4,500 weight tiles to read",
        11.5,
        c["mute"],
    )
    x0, x1, sy = 30, W - 30, top + 56
    k = (x1 - x0) / TILES
    for i in range(120):
        a, b = FIRST[i], FIRST[i + 1]
        edge, mid, pale = c["w"]
        fill = edge if i == 1 else mid if i % 2 else pale
        s.rect(x0 + a * k, sy, (b - a) * k, 16, fill, edge, rx=0, sw=0.5)
    s.text(x0, sy + 30, "core 0", 11, c["mute"])
    s.text(x1, sy + 30, "core 119", 11, c["mute"], anchor="end")
    cx = x0 + 16.5 * k
    ky = top + 116
    kx, kw, kh = 200, 600, 246
    s.poly(
        [(cx, sy + 18), (cx, ky - 22), (kx + 20, ky - 22), (kx + 20, ky - 2)], "w", 1.2
    )
    s.text(
        kx + 28,
        ky - 8,
        "core 1: receivers 12-20, 177 entries (82 dense slices, 95 low-rank), "
        "4,525 weight tiles",
        11.5,
        c["w"][0],
        True,
    )
    s.rect(kx, ky, kw, kh, c["bg"], c["w"][0], rx=6, sw=1.4, layer=0)
    dx, dw = 30, 152
    s.rect(dx, ky, dw, kh, c["dram"], "none", rx=6, layer=0)
    s.text(dx + 10, ky + 18, "DRAM", 12, c["fg"], True)
    rows = (
        ("table", "the core's entries,", "4 KiB pages", "g"),
        ("w", "weights, bfp8_b,", "tiles transposed", "a"),
        ("x", "elements.radiance,", "bfloat16 tiles", "w"),
        ("y", "elements.irradiance,", "float32 tiles", "r"),
    )
    for i, (name, a, b, colour) in enumerate(rows):
        yy = ky + 28 + i * 54
        chip(s, dx + 8, yy, dw - 16, 48, name, colour, sub=a)
        s.text(dx + 16, yy + 44, b, 11, c["mute"])
    for name, yy in (
        ("mover A", ky + 38),
        ("compute", ky + 122),
        ("mover B", ky + 206),
    ):
        s.text(kx + 12, yy + 4, name, 12, c["w"][0], True)
    ax = kx + 86
    chip(s, ax, ky + 22, 120, 32, "table pages", "g", mono=False, size=11.5)
    chip(s, ax + 130, ky + 22, 150, 32, "its share of x, w", "g", mono=False, size=11.5)
    chip(s, ax, ky + 190, 150, 32, "its share of x, w", "g", mono=False, size=11.5)
    chip(s, ax + 160, ky + 190, 120, 32, "y's tiles out", "r", mono=False, size=11.5)
    s.line(dx + dw - 8, ky + 52, ax - 4, ky + 36, "g", 1.2)
    s.line(dx + dw - 8, ky + 106, ax + 126, ky + 50, "a", 1.2)
    s.line(dx + dw - 8, ky + 160, ax - 4, ky + 202, "w", 1.2)
    s.line(ax + 160, ky + 214, dx + dw - 8, ky + 222, "r", 1.2)
    ux = ax
    for name, sub, w, colour in (
        ("unpack", "x, w tiles", 80, "g"),
        ("math: matmul_block", "32x32 by 32x32", 142, "a"),
        ("pack", "onto own sums", 104, "r"),
    ):
        chip(s, ux, ky + 104, w, 40, name, colour, sub=sub, mono=False, size=11.5)
        ux += w + 8
    s.line(ax + 205, ky + 56, ax + 40, ky + 102, "g", 1.2)
    s.line(ax + 75, ky + 188, ax + 40, ky + 146, "g", 1.2)
    lx, lw = ux + 4, kx + kw - ux - 16
    s.rect(lx, ky + 70, lw, 120, c["y"][2], c["y"][0], rx=4, sw=1)
    s.text(lx + 8, ky + 87, "L1", 12, c["y"][0], True)
    for i, (label, colour) in enumerate(
        (("sums: 9 y tiles", "r"), ("t: V^T x", "m"), ("x_in, w_in", "w"))
    ):
        chip(
            s, lx + 8, ky + 96 + i * 30, lw - 16, 24, label, colour, mono=False, size=11
        )
    s.line(ux - 8, ky + 118, lx + 6, ky + 108, "r", 1.4)
    s.text(
        kx + 12,
        ky + kh - 10,
        "dense slice: K tiles of x by K x n of w; low-rank: V's products into t, "
        "then U^T's into the sums",
        11,
        c["mute"],
    )
    s.text(
        30,
        top + h - 10,
        "Sponza: one apply 2,609.3 us; Bistro interior (774,298 tiles) 4,288.0 us; "
        "120 cores of one P150A at 1,350 MHz.",
        11.5,
        c["fg"],
    )
    return top + h


def passes_panel(s, top):
    c = s.c
    h = 124
    panel(
        s,
        top,
        h,
        "The bounces: one apply a pass",
        "r",
        "the control bounces, 2 by default",
    )
    y = top + 42
    items = (
        ("L0", "sun, lamps, sky", "y", 112),
        ("apply", "E1 = M L0", "a", 104),
        ("x albedo / pi", "", "g", 104),
        ("apply", "E2 = M (a/pi E1)", "a", 130),
        ("E1 + E2 + sky", "", "r", 118),
        ("the field", "its voxels", "b", 92),
    )
    x = 30
    for i, (label, sub, colour, w) in enumerate(items):
        chip(s, x, y, w, 40, label, colour, sub=sub or None, mono=False, size=12)
        if i < len(items) - 1:
            s.line(x + w + 2, y + 20, x + w + 18, y + 20, "g", 1.4)
        x += w + 20
    s.text(
        30,
        top + h - 14,
        "The X280 cores between the applies: y fetched and added, the next x stored; "
        "then the field's values, scale and texels.",
        11,
        c["mute"],
    )
    return top + h


def transport(theme):
    s = Svg(theme, "The light transport as tiles on the matrix engines", W)
    y = matrix_panel(s, 12)
    y = apply_panel(s, y + 12)
    y = passes_panel(s, y + 12)
    return s.finish(y + 12)


if __name__ == "__main__":
    write({"transport": transport}, sys.argv[1] if len(sys.argv) > 1 else None)
