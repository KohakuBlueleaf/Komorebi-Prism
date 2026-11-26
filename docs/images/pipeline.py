"""Draws the README's figures as docs/images/<name>-{light,dark}.svg: teaser (a frame
drawn by the card alone: the host, the frame's thread and its four phases, a Tensix core
running a tile thread's steps with its planes in L1, the job thread's field update) and
frame (the eye's view on the cores in time, both forms; one tile thread on one core).

usage: python docs/images/pipeline.py [output folder]    (the standard library only)

Every name is the code's: the tile threads of src/prism/program/threads/tiles.py, the
steps' declarations, the dispatcher's phases (src/prism/program/dispatch/c/), the
field graph's commands (src/prism/stages/indirect/field_update/graph.py). The numbers
are copied from measurements/threads_account/README.md: Sponza's overview at
1,920 x 1,080, the frames of the tables "Four ways of handing out" and the pack CPU's
times of "Each CPU by step inside a tile thread".
"""

import sys
from pathlib import Path
from xml.sax.saxutils import escape

REPO = Path(__file__).resolve().parents[2]

THEMES = {
    "light": {
        "bg": "#ffffff",
        "fg": "#1f2328",
        "mute": "#59636e",
        "box": "#f6f8fa",
        "line": "#d1d9e0",
        "cell": "#eaeef2",
        "dram": "#d5dde6",
        "rule": "#818b98",
        "ink": "#ffffff",
        "a": ("#bc4c00", "#ffc999", "#fff1e5"),
        "b": ("#1b7c83", "#a6e0e3", "#dff5f5"),
        "m": ("#8250df", "#d8c5fb", "#f1e8ff"),
        "w": ("#0969da", "#a5d4ff", "#ddf4ff"),
        "r": ("#1a7f37", "#a6e3b5", "#dafbe1"),
        "p": ("#bf3989", "#f7c0de", "#ffeff7"),
        "y": ("#9a6700", "#ffe27a", "#fff8c5"),
        "g": ("#818b98", "#eaeef2", "#f6f8fa"),
    },
    "dark": {
        "bg": "#0d1117",
        "fg": "#e6edf3",
        "mute": "#9198a1",
        "box": "#161b22",
        "line": "#3d444d",
        "cell": "#21262d",
        "dram": "#2d3540",
        "rule": "#6e7681",
        "ink": "#0d1117",
        "a": ("#f0883e", "#6b3a14", "#2d1a0c"),
        "b": ("#39c5cf", "#14555a", "#0b2f33"),
        "m": ("#a371f7", "#4a2f85", "#2a1a4d"),
        "w": ("#4493f8", "#1d4b99", "#0c2d6b"),
        "r": ("#3fb950", "#1b5e2e", "#0f2d1a"),
        "p": ("#db61a2", "#7a2a57", "#3a1229"),
        "y": ("#d29922", "#6b4e0a", "#3a2d0a"),
        "g": ("#6e7681", "#21262d", "#161b22"),
    },
}

SANS = "-apple-system, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, 'DejaVu Sans Mono', monospace"
MONO_WIDTH = 0.602  # of the font size: DejaVu Sans Mono and Menlo


def width(text, size=12, bold=False, mono=False):
    """A text's width in pixels, generous for the sans fonts GitHub may use."""
    if mono:
        return MONO_WIDTH * size * len(text)
    return (0.6 if bold else 0.56) * size * len(text)


class Svg:
    """A figure in three layers (boxes, text and bars, arrows and chips)."""

    def __init__(self, theme, title, w, markers="abmwrpyg"):
        self.c = THEMES[theme]
        self.title, self.w, self.markers = title, w, markers
        self.layers = [[], [], []]

    def add(self, text, layer=1):
        self.layers[layer].append(text)

    def finish(self, height):
        c = self.c
        defs = "".join(
            f'<marker id="h{name}" viewBox="0 0 10 10" refX="9" refY="5" '
            f'markerWidth="5" markerHeight="5" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{c[name][0]}"/></marker>'
            for name in self.markers
        )
        head = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" '
            f'height="{height}" viewBox="0 0 {self.w} {height}" role="img">\n'
            f"<title>{escape(self.title)}</title>\n<defs>{defs}</defs>\n"
            f'<rect width="{self.w}" height="{height}" fill="{c["bg"]}"/>'
        )
        body = [line for layer in self.layers for line in layer]
        return "\n".join([head, *body, "</svg>"])

    def rect(self, x, y, w, h, fill, stroke="none", rx=4, sw=1, dash=None, layer=1):
        extra = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{extra}/>',
            layer,
        )

    def text(self, x, y, s, size=12, fill=None, bold=False, mono=False, anchor="start"):
        family = MONO if mono else SANS
        weight = ' font-weight="600"' if bold else ""
        self.add(
            f'<text x="{x:.1f}" y="{y:.1f}" font-family="{family}" '
            f'font-size="{size}"{weight} fill="{fill or self.c["fg"]}" '
            f'text-anchor="{anchor}" xml:space="preserve">{escape(s)}</text>'
        )

    def line(self, x1, y1, x2, y2, colour, sw=2.0, dash=None, head=True, tail=False):
        stroke = self.c[colour][0] if colour in self.markers else colour
        extra = f' stroke-dasharray="{dash}"' if dash else ""
        extra += f' marker-end="url(#h{colour})"' if head else ""
        extra += f' marker-start="url(#h{colour})"' if tail else ""
        self.add(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{stroke}" stroke-width="{sw}"{extra}/>',
            2,
        )

    def poly(self, points, colour, sw=2.0, dash=None):
        """Straight pieces through the points, an arrowhead at the end."""
        d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in points)
        extra = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(
            f'<path d="{d}" fill="none" stroke="{self.c[colour][0]}" '
            f'stroke-width="{sw}" stroke-linejoin="round" '
            f'marker-end="url(#h{colour})"{extra}/>',
            2,
        )

    def rule(self, x1, y1, x2, y2, sw=1.0, dash=None):
        """A plain line in the rule colour, no arrowhead."""
        extra = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{self.c["rule"]}" stroke-width="{sw}"{extra}/>',
            0,
        )

    def slot(self, x, y, name, colour="y", anchor="start"):
        """A slot's name as a mono chip; returns its right edge."""
        w = width(name, 11.5, mono=True) + 12
        left = x - w if anchor == "end" else x - w / 2 if anchor == "middle" else x
        edge, _, pale = self.c[colour]
        self.rect(left, y - 12, w, 17, pale, edge, rx=8, sw=1, layer=2)
        self.add(
            f'<text x="{left + 6:.1f}" y="{y + 0.5:.1f}" font-family="{MONO}" '
            f'font-size="11.5" fill="{self.c["fg"]}" xml:space="preserve">'
            f"{escape(name)}</text>",
            2,
        )
        return left + w


W = 1280  # the teaser's width


def box(s, x, y, w, h, title, tag, colour, fill_key="box"):
    c = s.c
    s.rect(x, y, w, h, c[fill_key], c[colour][0], rx=6, sw=1.4, layer=0)
    s.text(x + 12, y + 20, title, 14, c[colour][0], True)
    if tag:
        s.text(x + 12, y + 37, tag, 11.5, c["mute"])


def chip(s, x, y, w, h, label, colour, sub=None, mono=True, size=12):
    c = s.c
    edge, _, pale = c[colour]
    s.rect(x, y, w, h, pale, edge, rx=5, sw=1.2)
    if sub:
        s.text(x + 8, y + 16, label, size, c["fg"], True, mono=mono)
        s.text(x + 8, y + 31, sub, 11, c["mute"])
    else:
        s.text(
            x + w / 2,
            y + h / 2 + 4,
            label,
            size,
            c["fg"],
            True,
            mono=mono,
            anchor="middle",
        )


def teaser(theme):
    s = Svg(theme, "Komorebi-Prism: a frame as threads", W)
    c = s.c
    s.text(16, 26, "One frame, drawn by the card alone", 17, c["fg"], True)
    s.text(
        16,
        46,
        "the host sends FRAME; the frame's thread hands out threads by pulls; "
        "the core that takes a tile's thread runs every step of that tile",
        12.5,
        c["mute"],
    )
    top = 64
    # the host
    hx, hw, hh = 16, 232, 300
    box(s, hx, top, hw, hh, "the host", "prism.loop, prism_cli, the viewer", "g")
    yy = top + 62
    for line, mono in (
        ("scene.glb", True),
        ("prism_cli open: converted once", False),
        ("", False),
        ("each frame:", False),
        ("Loop.frame(camera)", True),
        ("camera -> view.camera", True),
        ("FRAME, one thread command", False),
        ("", False),
        ("after the frame's event:", False),
        ("display pages read back", False),
    ):
        if line:
            s.text(hx + 14, yy, line, 12, c["fg"], mono=mono)
        yy += 19
    # the frame's thread
    fx, fw = 300, 412
    box(
        s,
        fx,
        top,
        fw,
        hh,
        "the frame's thread",
        "X280 work cluster 1: four cores, " "each the port of 30 Tensix cores",
        "w",
    )
    phases = (
        ("a", "1  count pull", "ranges of 4 triangle blocks, to whichever core asks"),
        ("b", "2  sums", "a command: each core the slices of its rank"),
        ("g", "   running sum", "each layer's place a slice; lists checked"),
        ("p", "3  place pull", "the count's log replayed: each core its ranges"),
        ("g", "   steps' words", "each step's words of the frame's page"),
        ("r", "4  tile pull", "the next tile thread for the core that asks (prefer)"),
    )
    py = top + 52
    for colour, name, sub in phases:
        h = 36
        chip(s, fx + 14, py, fw - 28, h, name, colour, sub)
        py += h + 4
    # a Tensix core
    cx, cw = 768, W - 16 - 768
    box(
        s,
        cx,
        top,
        cw,
        hh,
        "a Tensix core, one of 120",
        "the handler work: mover A, " "mover B, unpack, math, pack",
        "r",
    )
    sy = top + 64
    s.text(
        cx + 14,
        sy,
        "mover A asks its port; the tile thread's steps, in order:",
        12,
        c["fg"],
    )
    steps = ("visibility", "material_lit", "light", "post")
    sx, gap = cx + 14, 8
    stw = (cw - 28 - gap * 3) / 4
    for i, name in enumerate(steps):
        chip(s, sx + i * (stw + gap), sy + 12, stw, 34, name, "r", size=11.5)
        if i:
            s.line(
                sx + i * (stw + gap) - gap + 1,
                sy + 29,
                sx + i * (stw + gap) - 1,
                sy + 29,
                "r",
                1.4,
            )
    # planes in L1
    ly = sy + 66
    s.text(cx + 14, ly, "kept in the core's L1 between the steps:", 12, c["fg"])
    edge, fill, _ = c["y"]
    s.rect(sx, ly + 10, cw - 28, 22, fill, edge, rx=4)
    s.text(
        sx + 8, ly + 25, "frame.visibility   20 float32 tiles", 11.5, c["fg"], mono=True
    )
    s2 = sx + (stw + gap)
    s.rect(s2, ly + 38, 2 * stw + gap, 22, fill, edge, rx=4)
    s.text(s2 + 8, ly + 53, "frame.surface  20 tiles", 11.5, c["fg"], mono=True)
    oy = ly + 84
    s.text(cx + 14, oy, "pages asked into L1: lists, textures, light", 12, c["mute"])
    s.text(
        cx + 14,
        oy + 18,
        "written: the tile's display page, nothing else",
        12,
        c["mute"],
    )
    s.text(
        cx + 14,
        oy + 40,
        "(display.picture, read back by the host)",
        11.5,
        c["mute"],
        mono=True,
    )
    # arrows host -> frame thread, frame thread <-> core
    s.line(hx + hw + 2, top + 160, fx - 3, top + 160, "w", 2.2)
    s.text(
        (hx + hw + fx) / 2, top + 152, "FRAME", 11.5, c["w"][0], True, anchor="middle"
    )
    s.line(fx - 3, top + 200, hx + hw + 2, top + 200, "g", 1.6, dash="5 3")
    s.text(
        (hx + hw + fx) / 2, top + 216, "pages", 11.5, c["mute"], True, anchor="middle"
    )
    s.line(fx + fw + 2, top + 128, cx - 3, top + 128, "r", 2.0)
    s.text(
        (fx + fw + cx) / 2, top + 120, "answer", 11.5, c["r"][0], True, anchor="middle"
    )
    s.line(cx - 3, top + 168, fx + fw + 2, top + 168, "r", 1.6, dash="5 3")
    s.text((fx + fw + cx) / 2, top + 184, "ask", 11.5, c["r"][0], True, anchor="middle")
    # the job thread
    jy, jh = top + hh + 22, 128
    jx, jw = 300, W - 16 - 300
    box(
        s,
        jx,
        jy,
        jw,
        jh,
        "gi_threads: the job thread",
        "X280 work clusters 2 and 3: "
        "the field's update, a graph kept on the card while frames go on",
        "m",
    )
    nodes = (
        ("job_wants", "the cores it wants", "w"),
        ("field_sources", "L0 of each element", "m"),
        ("apply", "on the lowest ranks", "r"),
        ("field_pass", "y added, next x", "m"),
        ("field_finish", "the field's pages", "m"),
        ("job_wants", "the half, the scale", "w"),
    )
    nx, ny = jx + 14, jy + 54
    nw = (jw - 28 - 5 * 18) / 6
    for i, (name, sub, colour) in enumerate(nodes):
        x = nx + i * (nw + 18)
        chip(s, x, ny, nw, 40, name, colour, sub, size=11.5)
        if i:
            s.line(x - 16, ny + 20, x - 2, ny + 20, "m", 1.4)
    loop_l = nx + 2 * (nw + 18)
    loop_r = nx + 3 * (nw + 18) + nw
    s.poly(
        [
            (loop_r - 10, ny + 41),
            (loop_r - 10, ny + 58),
            (loop_l + 10, ny + 58),
            (loop_l + 10, ny + 43),
        ],
        "m",
        1.4,
    )
    s.text(
        (loop_l + loop_r) / 2,
        ny + 70,
        "a round a bounce",
        11,
        c["mute"],
        anchor="middle",
    )
    # job thread -> frame thread
    s.line(fx + fw / 2, jy - 2, fx + fw / 2, top + hh + 2, "w", 1.6, dash="5 3")
    s.text(
        fx + fw / 2 + 8,
        jy - 7,
        "job_wants: the next frame reads the new half",
        11,
        c["mute"],
    )
    # left bottom: numbers
    nyy = jy
    s.rect(hx, nyy, hw, jh, c["box"], c["line"], rx=6, layer=0)
    s.text(hx + 12, nyy + 20, "Sponza, 1,920 x 1,080", 13, c["fg"], True)
    s.text(hx + 12, nyy + 37, "one P150A, ms a frame", 11.5, c["mute"])
    rows = (
        ("", "threads", "stage-wise"),
        ("textured", "13.134", "16.428"),
        ("lit", "14.584", "18.838"),
    )
    for i, (a, b, d) in enumerate(rows):
        y = nyy + 62 + i * 20
        bold = i == 0
        s.text(hx + 12, y, a, 12, c["fg"], bold, mono=not bold)
        s.text(hx + 140, y, b, 12, c["r"][0] if i else c["fg"], True, anchor="end")
        s.text(hx + hw - 12, y, d, 12, c["fg"], bold, anchor="end")
    s.text(
        hx + 12,
        nyy + jh - 10,
        "pictures equal; lit built with the account",
        11,
        c["mute"],
    )
    return s.finish(jy + jh + 16)


NUMS = (
    "count 1.041, sums 0.272, running sum 0.050, place 1.919, tile pull 11.301",
    (
        "count 0.944, sums 0.329, middle pass 2.028, place 0.339, set-up 1.528, "
        "fill to push 13.668"
    ),
)


def frame(theme):
    w = 830
    s = Svg(theme, "A frame as threads: the view's phases, and one tile thread", w)
    c = s.c
    x0, x1 = 16, w - 16
    # panel 1
    p1 = 12
    s.rect(x0, p1, x1 - x0, 214, c["box"], c["line"], layer=0)
    s.text(
        x0 + 14, p1 + 22, "The eye's view on the cores, in time", 14, c["w"][0], True
    )
    s.text(
        x1 - 14,
        p1 + 22,
        "Sponza overview, lit, 1,920 x 1,080, one P150A, ms",
        12,
        c["mute"],
        anchor="end",
    )
    left, right = x0 + 120, x1 - 20
    scale = (right - left) / 18.838
    rows = (
        (
            "threads",
            "prefer, 14.584",
            (
                ("count", 1.041, "a"),
                ("sums", 0.272, "b"),
                ("", 0.050, "g"),
                ("place", 1.919, "p"),
                ("tile pull", 11.301, "r"),
            ),
        ),
        (
            "stage-wise",
            "18.838",
            (
                ("count", 0.944, "a"),
                ("sums", 0.329, "b"),
                ("middle", 2.028, "g"),
                ("", 0.339, "p"),
                ("set-up", 1.528, "p"),
                ("fill, shade, light, show, push", 13.668, "r"),
            ),
        ),
    )
    for r, (name, total, parts) in enumerate(rows):
        y = p1 + 48 + r * 66
        s.text(x0 + 14, y + 17, name, 12.5, c["fg"], True)
        s.text(x0 + 14, y + 33, total, 11.5, c["mute"])
        x = left
        for label, ms, colour in parts:
            pw = ms * scale
            edge, fill, _ = c[colour]
            s.rect(x, y, pw, 26, fill, edge, rx=2, sw=1)
            if label and pw > width(label, 11) + 6:
                s.text(x + pw / 2, y + 17, label, 11, c["fg"], anchor="middle")
            x += pw
        s.text(left, y + 44, NUMS[r], 11, c["mute"])
    s.text(
        x0 + 14,
        p1 + 196,
        "Threads: the X280 between the pulls is the running sum "
        "(0.050). Stage-wise: the X280's middle pass (2.028) cuts heavy tiles and "
        "deals them.",
        11.5,
        c["mute"],
    )
    # panel 2
    p2 = p1 + 230
    ph = 330
    s.rect(x0, p2, x1 - x0, ph, c["box"], c["line"], layer=0)
    s.text(x0 + 14, p2 + 22, "One tile thread on one core", 14, c["r"][0], True)
    s.text(
        x1 - 14,
        p2 + 22,
        "pack's ms a frame a core by step (lit, order, median)",
        12,
        c["mute"],
        anchor="end",
    )
    lanes = (("mover A", "w"), ("mover B", "w"), ("compute", "r"), ("L1", "y"))
    lx = x0 + 100
    lw = x1 - 16 - lx
    lane_y = {}
    for i, (name, colour) in enumerate(lanes):
        y = p2 + 44 + i * 62
        lane_y[name] = y
        s.text(x0 + 14, y + 22, name, 12.5, c[colour][0], True)
        s.rule(lx, y + 52, x1 - 16, y + 52, dash="2 3")
    steps = (
        ("visibility", 2.77),
        ("material_lit", 4.91),
        ("light", 2.93),
        ("post", 0.05),
    )
    ask_w = 70
    total = sum(m for _, m in steps)
    avail = lw - ask_w - 12
    xs, x = [], lx + ask_w + 12
    for name, ms in steps:
        sw_ = max(ms / total * avail, 44)
        xs.append((x, sw_))
        x += sw_
    # rescale to fit
    over = (xs[-1][0] + xs[-1][1]) - (lx + lw)
    if over > 0:
        k = (avail - over) / avail
        x = lx + ask_w + 12
        new = []
        for (ox, ow), (name, ms) in zip(xs, steps):
            ow2 = max(ow * k, 44)
            new.append((x, ow2))
            x += ow2
        xs = new
    ya = lane_y["mover A"]
    chip(s, lx, ya + 6, ask_w, 38, "ask", "w", "port: 0.3 us", size=11.5)
    s.text(
        lx + ask_w + 18,
        ya + 22,
        "the descriptor to the compute CPUs and mover B;",
        11.5,
        c["fg"],
    )
    s.text(
        lx + ask_w + 18,
        ya + 38,
        "both movers serve the pages the steps ask for",
        11.5,
        c["fg"],
    )
    yb = lane_y["mover B"]
    labels_b = ("lists streamed", "lists, texture pages", "light pages", "")
    for (x, sw_), lab in zip(xs, labels_b):
        if lab:
            s.rect(x + 2, yb + 10, sw_ - 4, 28, c["cell"], c["line"], rx=3)
            s.text(x + sw_ / 2, yb + 28, lab, 11, c["fg"], anchor="middle")
    px, pw = xs[-1]
    yc = lane_y["compute"]
    for (x, sw_), (name, ms) in zip(xs, steps):
        edge, fill, _ = c["r"]
        s.rect(x + 1, yc + 6, sw_ - 2, 38, fill, edge, rx=3)
        lab = name if sw_ > width(name, 11, mono=True) + 6 else name[:4]
        s.text(x + sw_ / 2, yc + 22, lab, 11, c["fg"], True, mono=True, anchor="middle")
        s.text(x + sw_ / 2, yc + 37, f"{ms:.2f}", 10.5, c["fg"], anchor="middle")
    yl = lane_y["L1"]
    edge, fill, _ = c["y"]
    vx = xs[0][0]
    s.rect(vx + 1, yl + 4, xs[-1][0] + xs[-1][1] - vx - 2, 20, fill, edge, rx=3)
    s.text(vx + 8, yl + 18, "frame.visibility", 11, c["fg"], mono=True)
    sx = xs[1][0]
    s.rect(sx + 1, yl + 28, xs[2][0] + xs[2][1] - sx - 2, 20, fill, edge, rx=3)
    s.text(sx + 8, yl + 42, "frame.surface", 11, c["fg"], mono=True)
    # output block arrow from post to display page
    ox = px + pw / 2
    s.line(ox, yc + 4, ox, ya + 46, "r", 1.6)
    s.text(
        ox,
        ya + 2,
        "post's output block: converted by a mover,",
        11,
        c["fg"],
        anchor="end",
    )
    s.text(ox, ya + 15, "written to the tile's display page", 11, c["fg"], anchor="end")
    s.text(
        x0 + 14,
        p2 + ph - 14,
        "A DEPTH view of the sun runs visibility, "
        "material_lit and depth_out, which writes the tile's 1/z into the shadow map.",
        11.5,
        c["mute"],
    )
    return s.finish(p2 + ph + 12)


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "docs" / "images"
    out.mkdir(parents=True, exist_ok=True)
    figures = {"teaser": teaser, "frame": frame}
    for theme in THEMES:
        for name, draw in figures.items():
            (out / f"{name}-{theme}.svg").write_text(draw(theme) + "\n")


if __name__ == "__main__":
    main()
