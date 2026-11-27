"""Draws docs/images/threads-{light,dark}.svg: one frame in time on the cores, both forms
on one axis. Above, the threads' form (lit, the tile pull's choice prefer): each core
takes count ranges, place ranges and tile threads one after another as it frees up; a
tile thread's bar is coloured by its steps. Below, the stage-wise form of the same
frame: every command on every core, each core standing still until the slowest is done.

usage: python docs/images/threads.py [output folder]    (the standard library only)

Numbers: measurements/threads_account (Sponza's overview, 1,920 x 1,080, lit: the
phases of "Four ways of handing out", threads a core and spans of "A core's time" and
"What asking costs", pack's step times of "Each CPU by step"); the stage-wise frame's
last group split by command from measurements/account (lit, sponza, 1,920 x 1,080).
Where each core's threads lie inside a phase is drawn to those counts and spans with a
fixed seed; it is not one record.
"""

import random
import sys

from draw import Svg, write

FW = 880
X0, X1 = 118, FW - 16
SCALE = (X1 - X0) / 19.2  # px a ms
ROWS = tuple(range(0, 120, 11))  # the cores drawn, by rank
RH, RG = 15, 4

THREADS = (
    ("count", 1.041),
    ("sums", 0.272),
    ("running", 0.050),
    ("place", 1.919),
    ("tile", 11.301),
)
STEPS = (
    ("visibility", 2.77, "w"),
    ("material_lit", 4.91, "a"),
    ("light", 2.93, "y"),
    ("post", 0.05, "p"),
)
STAGEWISE = (
    ("count", 0.944, "w"),
    ("sums", 0.329, "w"),
    ("middle", 2.028, None),
    ("place", 0.339, "w"),
    ("set-up", 1.528, "w"),
    ("fill", 2.228 + 0.169, "w"),
    ("shade", 5.260 + 0.801, "a"),
    ("light", 3.099, "y"),
    ("show", 1.542, "p"),
    ("push", 0.564, None),
)
STILL = {
    "count": 0.505,
    "set-up": 0.662,
    "fill": 0.098,
    "shade": 0.642,
    "light": 0.288,
    "show": 0.089,
    "sums": 0.05,
    "place": 0.034,
}


def X(ms):
    return X0 + ms * SCALE


def axis(s, y, until):
    c = s.c
    s.rule(X0, y, X(until), y)
    for ms in range(0, int(until) + 1, 2):
        s.rule(X(ms), y, X(ms), y + 4)
        s.text(X(ms), y + 16, f"{ms}", 11, c["mute"], anchor="middle")
    s.text(X1, y + 16, "ms", 11, c["mute"], anchor="end")


def row_labels(s, y0):
    c = s.c
    s.text(X0 - 8, y0 + 12, "X280 1", 11.5, c["w"][0], True, anchor="end")
    for i, rank in enumerate(ROWS):
        y = y0 + (i + 1) * (RH + RG)
        s.text(X0 - 8, y + 12, f"core {rank}", 11.5, c["fg"], anchor="end")


def runs(s, rng, y, start, span, n, colour, shades=True):
    """n threads of random lengths filling start..start+span on a row."""
    c = s.c
    weights = [rng.lognormvariate(0, 0.5) for _ in range(n)]
    total = sum(weights)
    x = start
    for k, w in enumerate(weights):
        d = span * w / total
        fill = c[colour][1] if (k % 2 == 0 or not shades) else c[colour][2]
        s.rect(X(x), y, max(d * SCALE - 0.4, 0.6), RH, fill, c[colour][0], rx=1, sw=0.5)
        x += d


def tile_threads(s, rng, y, start, span, n):
    c = s.c
    weights = [rng.lognormvariate(0, 0.45) for _ in range(n)]
    total = sum(weights)
    x = start
    for w in weights:
        d = span * w / total
        parts = [ms * rng.uniform(0.7, 1.3) for _, ms, _ in STEPS]
        psum = sum(parts)
        xx = x
        for (_, _, colour), p in zip(STEPS, parts, strict=True):
            dd = d * p / psum
            s.rect(X(xx), y, max(dd * SCALE, 0.5), RH, c[colour][1], rx=0)
            xx += dd
        s.rect(X(x), y, d * SCALE - 0.6, RH, "none", c["fg"], rx=1, sw=0.5)
        x += d


def threads_panel(s, top):
    c = s.c
    s.text(
        16,
        top + 16,
        "the threads' form: lit_threads, tile pull prefer, 14.584 ms",
        13,
        c["r"][0],
        True,
    )
    y0 = top + 46
    t = 0.0
    edges = {}
    for name, ms in THREADS:
        edges[name] = (t, t + ms)
        t += ms
    labels = (("count", "count"), ("place", "place 1.92"), ("tile", "tile pull 11.30"))
    for name, text in labels:
        a, b = edges[name]
        s.text((X(a) + X(b)) / 2, y0 - 6, text, 11.5, c["fg"], True, anchor="middle")
    for name, (a, b) in edges.items():
        s.rule(X(b), y0 - 2, X(b), y0 + (len(ROWS) + 1) * (RH + RG), 0.8, "2 2")
    row_labels(s, y0)
    rng = random.Random(5)
    # the X280 row
    for name, (a, b) in edges.items():
        if name == "sums":
            continue
        dark = name == "running"
        s.rect(
            X(a),
            y0,
            (b - a) * SCALE,
            RH,
            c["w"][0] if dark else c["w"][2],
            c["w"][0],
            rx=1,
            sw=0.6,
        )
    s.text(
        X(edges["tile"][0]) + 6,
        y0 + 11.5,
        "answers every ask: dp_choose, 3.4 us a " "choice, 65 % of the pull busy",
        11,
        c["fg"],
    )
    for i, rank in enumerate(ROWS):
        y = y0 + (i + 1) * (RH + RG)
        a, b = edges["count"]
        runs(s, rng, y, a + 0.01, rng.uniform(0.39, 0.87), rng.randint(15, 21), "w")
        a, b = edges["sums"]
        if rank == 0:
            s.rect(X(a), y, 0.263 * SCALE, RH, c["g"][1], c["g"][0], rx=1, sw=0.5)
        a, b = edges["place"]
        span = 1.26 + 0.05 if rank == 55 else rng.uniform(0.53, 1.05)
        n = rng.randint(15, 21)
        if rank == 55:
            runs(s, rng, y, a + 0.01, 0.05, 3, "b")
            s.rect(X(a + 0.06), y, 1.26 * SCALE, RH, c["b"][1], c["b"][0], rx=1, sw=0.5)
        else:
            runs(s, rng, y, a + 0.01, span, n, "b")
        a, b = edges["tile"]
        span = (b - a) - (0.01 if rank == 77 else rng.uniform(0.1, 1.3))
        tile_threads(s, rng, y, a + 0.01, span, rng.randint(14, 20))
    yb = y0 + (len(ROWS) + 1) * (RH + RG)
    return yb, edges


def stagewise_panel(s, top):
    c = s.c
    s.text(
        16,
        top + 16,
        "the stage-wise form: lit, every command on every core, " "18.838 ms",
        13,
        c["g"][0],
        True,
    )
    y0 = top + 46
    t = 0.0
    edges = []
    for name, ms, colour in STAGEWISE:
        edges.append((name, t, t + ms, colour))
        t += ms
    for name, a, b, _ in edges:
        if b - a > 0.9:
            s.text(
                (X(a) + X(b)) / 2, y0 - 6, name, 11.5, c["fg"], True, anchor="middle"
            )
        s.rule(X(b), y0 - 2, X(b), y0 + (len(ROWS) + 1) * (RH + RG), 0.8, "2 2")
    row_labels(s, y0)
    rng = random.Random(9)
    for name, a, b, colour in edges:
        if name == "middle":
            s.rect(X(a), y0, (b - a) * SCALE, RH, c["w"][0], rx=1)
            s.text(X(a) + 4, y0 + 11.5, "middle pass", 11, c["ink"], True)
        else:
            s.line(X(a) + 1, y0 + 1, X(a) + 1, y0 + RH, "w", 1.6, head=False)
    for i, _ in enumerate(ROWS):
        y = y0 + (i + 1) * (RH + RG)
        for name, a, b, colour in edges:
            if colour is None:
                continue
            still = min(rng.uniform(0, 2 * STILL.get(name, 0.05)), (b - a) * 0.8)
            s.rect(
                X(a),
                y,
                max((b - a - still) * SCALE - 0.4, 0.6),
                RH,
                c[colour][1],
                c[colour][0],
                rx=1,
                sw=0.5,
            )
    a, b = edges[-1][1], edges[-1][2]
    s.text(X(b) + 3, y0 + (RH + RG) + 12, "push", 11, c["mute"], anchor="start")
    yb = y0 + (len(ROWS) + 1) * (RH + RG)
    return yb


def legend(s, y):
    c = s.c
    items = [
        (c["w"][1], "visibility, fill; count, set-up"),
        (c["b"][1], "place ranges"),
        (c["a"][1], "material_lit, shade"),
        (c["y"][1], "light"),
        (c["p"][1], "post, show"),
        (c["w"][2], "X280 1 answering"),
    ]
    x = 16
    for fill, name in items:
        s.rect(x, y - 10, 12, 12, fill, c["rule"], rx=2, sw=0.5)
        s.text(x + 17, y, name, 11.5, c["fg"])
        x += 30 + 6.2 * len(name)


def threads(theme):
    s = Svg(theme, "A frame in time on the cores: threads against commands", FW)
    c = s.c
    s.text(
        16, 22, "One frame on the cores, both forms on one time axis", 16, None, True
    )
    s.text(
        16,
        40,
        "Sponza's overview, 1,920 x 1,080, lit, one P150A; 11 of the 120 "
        "cores; a bar is a thread or a command on that core, blank is standing still",
        11.5,
        c["mute"],
    )
    yb, edges = threads_panel(s, 50)
    axis(s, yb + 4, 19)
    end = edges["tile"][1]
    yb2 = stagewise_panel(s, yb + 34)
    axis(s, yb2 + 4, 19)
    s.line(X(end), 92, X(end), yb2, "r", 1.4, dash="5 3", head=False)
    s.text(X(end) + 4, 108, "14.584", 11.5, c["r"][0], True)
    legend(s, yb2 + 42)
    notes = (
        (
            "Threads: a core asks for its next thread when its last ends (an ask is"
            " 0.3 us at the median); 14 to 20 tile threads a core;"
        ),
        (
            "the tile pull's end waits only for the last tile thread. Stage-wise: each"
            " command (a tick on X280 1's row) ends with its slowest core; the middle pass"
        ),
        (
            "(2.028 ms) holds every core. Phase times measured; each core's threads"
            " drawn to the measured counts and spans, not one record."
        ),
    )
    for k, line in enumerate(notes):
        s.text(16, yb2 + 66 + 15 * k, line, 11.5, c["mute"])
    return s.finish(yb2 + 66 + 15 * len(notes))


def main():
    write({"threads": threads}, sys.argv[1] if len(sys.argv) > 1 else None)


if __name__ == "__main__":
    main()
