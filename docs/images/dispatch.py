"""Draws docs/images/dispatch-{light,dark}.svg: how work reaches a core. The frame cut
into count ranges, slices and records; one pull between a core's mover A and its port
on X280 1; the tile pull's three ways of choosing; a layer's lists found too small and
grown while the run stays loaded.

usage: python docs/images/dispatch.py [output folder]    (the standard library only)

Names: docs/internals/program/dispatch.md and work.md (RANGE_BLOCKS 4, SLICE_TILES 16,
TR_SLICE_RECORDS 32, TR_NUMBER, TA_HINT_NEAR, dp_choose, DP_LISTS_SMALL, the need page,
ThreadsHost.needed, LIST_MARGIN 1.25, list_slots_least). Numbers: measurements/
threads_account (Sponza's overview, 1,920 x 1,080, textured: the tile pull by way; an
ask's median 0.3 us; prefer's 3.4 us a choice; 136 slices on 120 cores).
"""

import sys

from draw import Svg, chip, write

FW = 880
CORES = ("w", "a", "r")  # three cores of the policies' panel


def panel(s, x, y, w, h, title, colour="g"):
    c = s.c
    s.rect(x, y, w, h, c["box"], c["line"], rx=6, sw=1, layer=0)
    s.text(x + 12, y + 20, title, 13, c[colour][0], True)


def cut(s, x, y, w):
    c = s.c
    panel(s, x, y, w, 300, "the cut: what a thread is", "w")
    # triangle blocks into count ranges
    s.text(
        x + 12, y + 42, "a layer's triangle blocks (32 triangles each)", 11.5, c["fg"]
    )
    bx, by, bw = x + 12, y + 50, 26
    for k in range(14):
        s.rect(bx + k * (bw + 2), by, bw, 16, c["cell"], c["rule"], rx=2, sw=0.6)
    for r in range(4):
        a = bx + r * 4 * (bw + 2)
        b = min(a + 4 * (bw + 2) - 2, bx + 14 * (bw + 2) - 2)
        s.rule(a, by + 22, b, by + 22, 1.6)
        s.text((a + b) / 2, by + 36, f"range {r}", 11, c["w"][0], True, anchor="middle")
    s.text(
        x + 12,
        by + 54,
        "a count range: 4 blocks on Sponza (set by the scene); counted, then placed",
        11.5,
        c["fg"],
    )
    # a row of tiles into slices
    ty = by + 80
    s.text(x + 12, ty, "a row of the frame: 60 tiles of 32 x 32 pixels", 11.5, c["fg"])
    t = (w - 24) / 60
    for k in range(60):
        sl = k // 16
        s.rect(
            x + 12 + k * t, ty + 8, t - 1, 14, c["a"][1] if sl == 1 else c["cell"], rx=1
        )
    for sl in range(4):
        a = x + 12 + sl * 16 * t
        b = x + 12 + min(sl * 16 + 16, 60) * t - 1
        s.rule(a, ty + 28, b, ty + 28, 1.6)
        s.text(
            (a + b) / 2,
            ty + 42,
            f"slice {sl}",
            11,
            c["a"][0] if sl == 1 else c["mute"],
            True,
            anchor="middle",
        )
    # a slice's records
    ry = ty + 60
    s.text(
        x + 12,
        ry,
        "slice 1's records, in order of weight: a record is a tile " "thread",
        11.5,
        c["fg"],
    )
    weights = (1.0, 0.82, 0.7, 0.55, 0.47, 0.4, 0.31, 0.22, 0.15, 0.08)
    for k, wt in enumerate(weights):
        xx = x + 12 + k * 38
        s.rect(
            xx, ry + 10 + (1 - wt) * 34, 30, wt * 34, c["a"][1], c["a"][0], rx=2, sw=0.6
        )
        s.text(xx + 15, ry + 58, f"{32 + k}", 11, c["fg"], mono=True, anchor="middle")
    s.text(
        x + 12,
        ry + 76,
        "number = slice x 32 + place (TR_NUMBER); a tile past " "the weight",
        11.5,
        c["mute"],
    )
    s.text(
        x + 12,
        ry + 90,
        "heavy is cut into bands of its rows, a record each",
        11.5,
        c["mute"],
    )


def pull(s, x, y, w):
    c = s.c
    panel(s, x, y, w, 300, "a pull: the core asks, its port answers", "w")
    la, lb = x + 70, x + w - 70
    for lx, name, colour in ((la, "mover A", "r"), (lb, "port, X280 1", "w")):
        chip(s, lx - 55, y + 34, 110, 24, name, colour, size=12, mono=False)
        s.rule(lx, y + 60, lx, y + 252, 1, "4 3")
    msgs = (
        (y + 84, "tell: the ended thread's", "number, its cost, codes held", "r", True),
        (y + 118, "ask", "", "r", True),
        (y + 148, "answer: a record's number,", "its word (code 0, near?)", "w", False),
        (y + 236, "answer 0: none left", "the core's part ends", "w", False),
    )
    for yy, a, b, colour, right in msgs:
        if right:
            s.line(la + 2, yy, lb - 2, yy, colour, 1.6)
        else:
            s.line(lb - 2, yy, la + 2, yy, colour, 1.6)
        s.text((la + lb) / 2, yy - 6, a, 11.5, c["fg"], True, anchor="middle")
        if b:
            s.text((la + lb) / 2, yy + 14, b, 11, c["mute"], anchor="middle")
    s.text(lb + 6, y + 116, "the answer", 11, c["mute"])
    s.text(lb + 6, y + 130, "is waiting:", 11, c["mute"])
    s.text(lb + 6, y + 144, "0.3 us", 11, c["w"][0], True)
    s.rect(la - 8, y + 168, 16, 52, c["r"][1], c["r"][0], rx=2, sw=0.8)
    s.text(la + 14, y + 184, "the descriptor to the compute", 11, c["fg"])
    s.text(la + 14, y + 198, "CPUs and mover B; the thread", 11, c["fg"])
    s.text(la + 14, y + 212, "runs; one more taken ahead", 11, c["fg"])
    s.text(
        x + 12,
        y + 270,
        "the count pull: whoever asks gets the next range (logged);",
        11,
        c["mute"],
    )
    s.text(
        x + 12,
        y + 284,
        "the place pull replays the log; the tile pull asks dp_choose",
        11,
        c["mute"],
    )


def policies(s, y):
    c = s.c
    panel(
        s,
        16,
        y,
        FW - 32,
        206,
        "the tile pull's choice (the option policy): which "
        "slice the core that asks gets next",
        "a",
    )
    cols, rows, cell = 4, 6, 22
    ways = (
        (
            "prefer",
            "a slice within near (1) of the core's",
            "last, heaviest first: its pages may",
            "still be held",
            "9.930",
        ),
        (
            "order",
            "the next slice with records left,",
            "one cursor for every core",
            "",
            "10.647",
        ),
        (
            "kept",
            "slice s to core s mod cores,",
            "kept; 136 slices on 120 cores:",
            "16 cores take two",
            "20.243",
        ),
    )
    owner = {
        "prefer": [
            0,
            0,
            1,
            1,
            0,
            0,
            1,
            1,
            0,
            2,
            2,
            1,
            0,
            2,
            2,
            1,
            2,
            2,
            0,
            1,
            2,
            0,
            0,
            1,
        ],
        "order": [
            0,
            1,
            2,
            0,
            2,
            1,
            1,
            0,
            2,
            0,
            1,
            2,
            2,
            0,
            1,
            1,
            0,
            2,
            0,
            2,
            1,
            2,
            0,
            1,
        ],
        "kept": [k % 3 for k in range(24)],
    }
    seq = {"order": list(range(24)), "kept": [k % 3 for k in range(24)]}
    pw = (FW - 32) / 3
    for i, (name, l1, l2, l3, ms) in enumerate(ways):
        x = 16 + i * pw + 14
        gy = y + 34
        for k in range(cols * rows):
            r, q = divmod(k, cols)
            colour = CORES[owner[name][k]]
            s.rect(
                x + q * (cell + 2),
                gy + r * (cell + 2),
                cell,
                cell,
                c[colour][1],
                c[colour][0],
                rx=2,
                sw=0.6,
            )
            if name in seq:
                s.text(
                    x + q * (cell + 2) + cell / 2,
                    gy + r * (cell + 2) + 15,
                    f"{seq[name][k]}",
                    11,
                    c["fg"],
                    anchor="middle",
                )
        tx = x + cols * (cell + 2) + 10
        s.text(tx, gy + 12, name, 13, c["fg"], True, mono=True)
        for k, line in enumerate((l1, l2, l3)):
            s.text(tx, gy + 30 + 14 * k, line, 11, c["fg"])
        s.text(tx, gy + 96, "tile pull", 11, c["mute"])
        s.text(tx, gy + 112, f"{ms} ms", 13, c["a"][0], True)
    s.text(
        30,
        y + 196,
        "Three cores' slices (colour) on part of the grid, drawn; "
        "the numbers: the order handed (order), the core (kept). Tile pull: Sponza, "
        "textured.",
        11,
        c["mute"],
    )


def lists(s, y):
    c = s.c
    panel(
        s,
        16,
        y,
        FW - 32,
        190,
        "a layer's lists too small for this camera: grown "
        "while the run stays loaded",
        "y",
    )
    lanes = (
        ("frame's thread", "w", y + 52),
        ("DRAM", "g", y + 96),
        ("host", "g", y + 140),
    )
    for name, colour, ly in lanes:
        s.text(28, ly + 4, name, 11.5, c[colour][0], True)
        s.rule(118, ly, FW - 30, ly, 1, "4 3")
    steps = (
        (126, y + 38, "running sum:", "entries > list slots", "w"),
        (270, y + 38, "DP_LISTS_SMALL", "before place writes", "w"),
        (270, y + 82, "need page", "view, each layer's entries", "y"),
        (432, y + 126, "ThreadsHost.needed", "lists of entries x 1.25", "g"),
        (614, y + 126, "rows written again", "list_slots_least kept", "g"),
        (614, y + 38, '"retry": FRAME', "again; place, tile", "r"),
    )
    for x, yy, a, b, colour in steps:
        chip(s, x, yy, 136 if x < 600 else 160, 34, a, colour, b, mono=True, size=11.5)
    s.line(262, y + 55, 268, y + 55, "w", 1.4)
    s.line(338, y + 73, 338, y + 80, "y", 1.4)
    s.poly([(406, y + 99), (500, y + 99), (500, y + 124)], "g", 1.4)
    s.line(570, y + 143, 612, y + 143, "g", 1.4)
    s.line(694, y + 124, 694, y + 74, "r", 1.4)
    s.text(
        140,
        y + 180,
        "A frame's ranges or slices past the build's capacity "
        "(DP_TOO_MANY, a larger frame) are answered by one reload instead.",
        11,
        c["mute"],
    )


def figure(theme):
    s = Svg(theme, "How work reaches a core: ranges, slices, pulls, choices", FW)
    c = s.c
    s.text(16, 22, "How work reaches a core: only when the core asks", 16, None, True)
    s.text(
        16,
        40,
        "every thread of a frame is a number the frame's thread hands to "
        "the core that asks for one",
        11.5,
        c["mute"],
    )
    half = (FW - 32 - 12) / 2
    cut(s, 16, 52, half)
    pull(s, 16 + half + 12, 52, half)
    policies(s, 364)
    lists(s, 582)
    return s.finish(782)


def main():
    write({"dispatch": figure}, sys.argv[1] if len(sys.argv) > 1 else None)


if __name__ == "__main__":
    main()
