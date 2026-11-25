"""Draws the README's figures as docs/images/<name>-{light,dark}.svg: teaser (what the
host sends, what the card runs by itself, what comes back, and what a preset is), frame
(a frame in time: the stages in order with the slots each reads and writes, the layers,
and the sun's commands outside the frame), assembly (a preset becoming one program and
one thread, and what the core assigns) and light (where a pixel's light comes from: the
terms LIGHT adds and the indirect field the card updates).

usage: python docs/images/pipeline.py [output folder]    (needs Pillow, for the two
thumbnails of the teaser, cut from the viewer guide's pictures)

Every name is the code's: the presets of configs/pipeline, the implementations'
declarations, the slots of src/prism_common/slots.py, the units' roles and served
commands. The numbers are copied from committed pages: the frame's parts from
measurements/lit_frame/README.md (the frame's table and the layers' table,
bistro_interior at 1,024 x 1,024), the card frames from the records' READMEs
(raster_show, textured_show, lit_frame, gi_frame), the element count from
docs/concepts/scenes.md.
"""

import base64
import io
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image

REPO = Path(__file__).resolve().parents[2]
VIEWER = REPO / "docs" / "guides" / "viewer"

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
BOX_X, BOX_W = 16, 798  # a body figure's panels (830 wide)


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


def panel_frame(s, y, height, title, tag, colour, x=BOX_X, w=BOX_W):
    c = s.c
    s.rect(x, y, w, height, c["box"], c["line"], layer=0)
    s.text(x + 14, y + 22, title, 14, c[colour][0], True)
    if tag:
        s.text(x + w - 14, y + 22, tag, 12, c["mute"], anchor="end")


def key_row(s, x, y, right, items, note=()):
    """A key that wraps: (kind, text) pairs, then lines of note; returns its end."""
    c = s.c
    start = x
    for kind, text in items:
        need = 30 + width(text) + 22
        if x + need - 22 > right:
            x, y = start, y + 24
        if kind.startswith("bar:"):
            edge, fill, _ = c[kind[4:]]
            s.rect(x, y, 22, 16, fill, edge, rx=3)
        elif kind.startswith("pale:"):
            edge, _, pale = c[kind[5:]]
            s.rect(x, y, 22, 16, pale, edge, rx=3, sw=1.4, dash="4 3")
        elif kind.startswith("slot:"):
            edge, _, pale = c[kind[5:]]
            s.rect(x, y + 1, 22, 14, pale, edge, rx=7)
        else:
            s.line(x, y + 8, x + 22, y + 8, kind)
        s.text(x + 30, y + 13, text, 12)
        x += need
    for i, line in enumerate(note):
        s.text(start, y + 38 + 18 * i, line, 12, c["mute"])
    return y + 38 + 18 * len(note) - 8


class Lanes:
    """Rows in time: a name and a line each, bars on them and arrows between them."""

    def __init__(self, s, y, names, x0, x1, pitch=30):
        self.s, self.x0, self.x1 = s, x0, x1
        self.top = {name: y + k * pitch for k, name in enumerate(names)}
        self.bottom = y + len(names) * pitch - (pitch - 16)
        for name in names:
            cy = self.top[name] + 8
            s.text(x0 - 12, cy + 4, name, 12, s.c["mute"], anchor="end")
            s.add(
                f'<line x1="{x0:.1f}" y1="{cy:.1f}" x2="{x1:.1f}" y2="{cy:.1f}" '
                f'stroke="{s.c["line"]}" stroke-width="1"/>',
                0,
            )

    def tx(self, t):
        return self.x0 + (self.x1 - self.x0) * t / 100

    def bar(self, name, begin, end, text, colour, style="fill"):
        s, c = self.s, self.s.c
        edge, fill, pale = c[colour]
        x, yy, w = self.tx(begin), self.top[name], self.tx(end) - self.tx(begin)
        if style == "pale":
            s.rect(x, yy, w, 16, pale, edge, rx=3, sw=1.4, dash="4 3")
        else:
            s.rect(x, yy, w, 16, fill, edge, rx=3)
        if text and width(text, 11.5) + 8 <= w:
            s.text(x + w / 2, yy + 12, text, 11.5, c["fg"], anchor="middle")

    def hop(self, start, end, t, colour, dash=None, sw=1.8):
        """An arrow at time t from one row to another."""
        down = self.top[end] > self.top[start]
        y1 = self.top[start] + (17 if down else -1)
        y2 = self.top[end] + (-2 if down else 18)
        self.s.line(self.tx(t), y1, self.tx(t), y2, colour, sw, dash=dash)

    def axis(self, label="time (schematic)"):
        s = self.s
        s.add(
            f'<line x1="{self.x0:.1f}" y1="{self.bottom + 10:.1f}" '
            f'x2="{self.x1:.1f}" y2="{self.bottom + 10:.1f}" '
            f'stroke="{s.c["rule"]}" stroke-width="1.6" marker-end="url(#hg)"/>',
            2,
        )
        s.text(self.x1, self.bottom + 28, label, 12, s.c["mute"], anchor="end")
        return self.bottom + 28


# ---------------------------------------------------------------------------
# What the figures name: the presets, the implementations, their slots.
# ---------------------------------------------------------------------------

# configs/pipeline/*.py: each preset's implementations, in order
PRESETS = {
    "apply": ["indirect.transport"],
    "field": ["indirect.transport", "indirect.field_update"],
    "raster": ["raster", "post.show"],
    "textured": ["raster", "material.texture", "post.show"],
    "lit": [
        "raster",
        "material.texture",
        "direct.shadow_pcf",
        "direct.light",
        "post.show",
    ],
    "gi": [
        "raster",
        "material.texture",
        "direct.shadow_pcf",
        "indirect.transport",
        "indirect.field_update",
        "direct.light",
        "post.show",
    ],
}
# each implementation's declaration (__init__.py): the item it fills, its class (None:
# a unit and a host alone), its unit's role or served commands
DECLARED = {
    "raster": ("raster", "Raster", "layer"),
    "material.texture": ("material", "Shade", "layer"),
    "direct.shadow_pcf": (None, None, "serves sun"),
    "indirect.transport": ("indirect", "Apply", "serves apply; gives a pass"),
    "indirect.field_update": (None, None, "serves update, field_scale"),
    "direct.light": ("direct", "Light", "frame"),
    "post.show": ("post", "Show", "frame"),
}

# the frame's parts, ms: bistro_interior, 1,024 x 1,024, the preset lit
# (measurements/lit_frame/README.md, the layers' table and the frame's table)
FRAME_MS = 18.136
PARTS = [
    ("raster", "opaque", 5.601),
    ("raster", "masked", 1.207),
    ("raster", "glass", 2.260),
    ("SHADE", "opaque", 3.653),
    ("SHADE", "masked", 0.299),
    ("SHADE", "glass", 0.709),
    ("LIGHT", "", 3.262),
    ("SHOW", "", 0.863),
    ("PUSH", "", 0.287),
]
# measurements/{raster_show,textured_show,lit_frame,gi_frame}/README.md,
# sponza_overview at 1,024 x 1,024: the card frame in ms
FRAMES = [
    ("raster", "4.962"),
    ("textured", "10.781"),
    ("lit", "12.050"),
    ("gi", "14.267"),
]
# the teaser's pictures: the viewer guide's, the frame cut out; the card frame of the
# same preset, scene and size in lit_frame's and textured_show's README
PICTURES = [
    ("lit_sponza_default.png", (292, 85, 932, 725), "lit", "sponza", "12.050 ms"),
    (
        "textured_bistro_interior.png",
        (292, 85, 932, 725),
        "textured",
        "bistro_interior",
        "15.442 ms",
    ),
]


def jpeg_uri(name, box, side):
    image = Image.open(VIEWER / name).convert("RGB").crop(box)
    image = image.resize((side, side), Image.LANCZOS)
    data = io.BytesIO()
    image.save(data, "JPEG", quality=84, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(data.getvalue()).decode()


# ---------------------------------------------------------------------------
# The teaser.
# ---------------------------------------------------------------------------


def teaser_host(s, x, y, w):
    """What the host sends: the camera, one FRAME command; a preset beside it."""
    c = s.c
    h = 176
    s.rect(x, y, w, h, c["box"], c["line"])
    s.text(x + 14, y + 24, "each frame", 13.5, bold=True)
    s.text(x + 14, y + 46, "Loop.frame(camera)", 12.5, c["w"][0], mono=True)
    lines = [
        ("the hosts' views:", "the camera written"),
        ("into the run;", ""),
        ("then one thread command:", ""),
    ]
    for i, (a, b) in enumerate(lines):
        s.text(x + 14, y + 70 + 18 * i, a + (" " + b if b else ""), 12, c["mute"])
    s.slot(x + 14, y + 128, "view.camera")
    s.text(x + 14 + width("view.camera", 11.5, mono=True) + 20, y + 128, "16 numbers")
    s.rect(x + 14, y + 142, 70, 22, c["w"][1], c["w"][0], rx=3)
    s.text(x + 49, y + 157, "FRAME", 12, c["fg"], True, anchor="middle")
    s.text(x + 92, y + 157, "to the director", 12, c["mute"])
    py = y + h + 14
    rows = PRESETS["lit"]
    ph = 52 + 20 * len(rows) + 46
    s.rect(x, py, w, ph, c["box"], c["line"])
    s.text(x + 14, py + 24, "a preset", 13.5, bold=True)
    s.text(
        x + w - 14, py + 24, "configs/pipeline/lit.py", 11.5, c["mute"], anchor="end"
    )
    s.text(x + 14, py + 44, "item", 11.5, c["mute"])
    s.text(x + 96, py + 44, "its implementation", 11.5, c["mute"])
    for i, name in enumerate(rows):
        item = DECLARED[name][0] or "-"
        ry = py + 64 + 20 * i
        s.text(x + 14, ry, item, 12, c["fg"] if DECLARED[name][0] else c["mute"])
        s.text(x + 96, ry, f'"{name}"', 12, c["a"][0], mono=True)
    ny = py + 64 + 20 * len(rows) + 4
    s.text(x + 14, ny, "One implementation an item; the", 12, c["mute"])
    s.text(x + 14, ny + 18, "list is resolved once, at the build.", 12, c["mute"])
    return py + ph


def teaser_grid(s, x, y):
    """The Tensix grid as 12 columns by 10 rows of cells (its two panels)."""
    c = s.c
    pitch, cell = 13, 11
    for row in range(10):
        for k in range(12):
            px = x + k * pitch + (14 if k >= 6 else 0)
            s.rect(px, y + row * pitch, cell, cell, c["a"][1], c["a"][0], rx=2, sw=0.6)
    return x + 12 * pitch + 14, y + 10 * pitch


def teaser_card(s, x, y, w, h):
    """The card by itself: the director's sequence, the grid, the frame in time."""
    c = s.c
    s.rect(x, y, w, h, c["bg"], c["a"][0], rx=6, sw=1.8)
    # the director, on X280 cluster 1
    dx, dy, dw = x + 16, y + 16, 300
    s.rect(dx, dy, dw, 146, c["box"], c["w"][0], rx=4, sw=1.6)
    s.text(dx + 12, dy + 21, "the director", 13.5, c["w"][0], True)
    s.text(dx + dw - 12, dy + 21, "X280 cluster 1", 12, c["mute"], anchor="end")
    steps = [
        ("raster", "each layer"),
        ("material.texture", "each layer"),
        ("direct.light", "the view"),
        ("post.show", "the view, then PUSH"),
    ]
    for i, (name, what) in enumerate(steps):
        ry = dy + 46 + 20 * i
        s.text(dx + 12, ry, f"{i + 1}", 12, c["mute"])
        s.text(dx + 30, ry, name, 12, c["fg"], mono=True)
        s.text(dx + 168, ry, what, 12, c["mute"])
    s.text(dx + 12, dy + 134, "dr_view: unit by unit, in the preset's order", 11.5)
    # the grid
    gx, gy = x + w - 16 - 182, y + 34
    s.text(gx, y + 24, "120 Tensix cores", 13, bold=True)
    _, bottom = teaser_grid(s, gx, gy)
    s.text(gx, bottom + 18, "one program on every core", 12, c["mute"])
    ay = dy + 56
    s.line(dx + dw + 4, ay, gx - 6, ay, "a", 2.2)
    s.text((dx + dw + gx) / 2, ay - 8, "commands", 12, c["a"][0], True, anchor="middle")
    s.line(gx - 6, ay + 26, dx + dw + 4, ay + 26, "r", 2.0)
    s.text((dx + dw + gx) / 2, ay + 44, "events", 12, c["r"][0], True, anchor="middle")
    # the frame in time
    ty = y + 204
    s.rule(x + 16, ty - 10, x + w - 16, ty - 10)
    s.text(
        x + 16, ty + 14, "one lit frame: bistro_interior, 1,024 x 1,024", 14, None, True
    )
    s.text(x + w - 16, ty + 14, f"{FRAME_MS:.3f} ms", 14, c["a"][0], True, anchor="end")
    lx0, lx1 = x + 128, x + w - 20
    span = sum(ms for *_, ms in PARTS)
    scale = (lx1 - lx0) / span
    lanes = [("host", ty + 36), ("director", ty + 72), ("Tensix cores", ty + 108)]
    for name, ly in lanes:
        s.text(x + 16, ly + 15, name, 12.5, bold=True)
        s.add(
            f'<line x1="{lx0:.1f}" y1="{ly + 11:.1f}" x2="{lx1:.1f}" '
            f'y2="{ly + 11:.1f}" stroke="{c["line"]}" stroke-width="1"/>',
            0,
        )
    hy, dy2, cy = (ly for _, ly in lanes)
    s.rect(lx0, hy, 46, 22, c["w"][1], c["w"][0], rx=3)
    s.text(lx0 + 23, hy + 15, "FRAME", 11, c["fg"], True, anchor="middle")
    s.line(lx0 + 23, hy + 24, lx0 + 23, dy2 - 2, "w", 1.8)
    s.rect(lx0, dy2 + 6, lx1 - lx0, 10, c["w"][2], rx=2)
    t = lx0
    colours = {"raster": "a", "SHADE": "y", "LIGHT": "p", "SHOW": "b", "PUSH": "b"}
    for name, layer, ms in PARTS:
        pw = ms * scale
        edge, fill, _ = c[colours[name]]
        s.rect(t + 0.5, cy, max(pw - 1, 1.5), 22, fill, edge, rx=2)
        if pw > 34:
            s.text(t + pw / 2, cy + 15, f"{ms:.2f}", 11, c["fg"], anchor="middle")
            s.text(t + pw / 2, cy + 38, name, 11.5, c["mute"], True, anchor="middle")
            if layer:
                s.text(t + pw / 2, cy + 54, layer, 11, c["mute"], anchor="middle")
        elif layer:
            s.text(t + pw / 2, cy + 54, layer[0], 11, c["mute"], anchor="middle")
        s.line(t + 2, dy2 + 17, t + 2, cy - 2, "a", 1.2)
        t += pw
    push_end = t
    show = PARTS[-2][2] * scale + PARTS[-1][2] * scale
    s.text(push_end - show / 2, cy + 38, "SHOW", 11.5, c["mute"], True, anchor="middle")
    s.text(push_end - show / 2, cy + 54, "PUSH", 11.5, c["mute"], True, anchor="middle")
    s.line(push_end - 2, cy - 2, push_end - 2, hy + 24, "b", 1.8)
    s.rect(push_end - 54, hy, 52, 22, c["b"][2], c["b"][0], rx=3)
    s.text(push_end - 28, hy + 15, "picture", 11, c["fg"], True, anchor="middle")
    s.text(
        lx0 + 60,
        hy + 15,
        "nothing from the host between the stages",
        12,
        c["mute"],
    )
    s.text(
        x + 16,
        cy + 76,
        "The layers' raster passes (COUNT to FILL) and SHADE, then LIGHT with its glass "
        "form, SHOW and the PUSH;",
        11.5,
        c["mute"],
    )
    s.text(
        x + 16,
        cy + 93,
        "the parts' medians, ms, from measurements/lit_frame. m: masked, g: glass.",
        11.5,
        c["mute"],
    )


def teaser_out(s, x, y, w, theme):
    """What comes back: pictures pushed by the card; the card frame by preset."""
    c = s.c
    side, gap = (w - 8) // 2, 8
    for i, (name, box, preset, scene, ms) in enumerate(PICTURES):
        px = x + i * (side + gap)
        uri = jpeg_uri(name, box, 2 * side)
        s.add(f'<image x="{px}" y="{y}" width="{side}" height="{side}" href="{uri}"/>')
        s.rect(px, y, side, side, "none", c["line"], rx=0)
        s.text(px, y + side + 16, preset, 12.5, c["a"][0], mono=True)
        s.text(px, y + side + 32, scene, 11.5)
        s.text(px, y + side + 48, ms + " a frame", 11.5, c["mute"])
    ty = y + side + 62
    s.rect(x, ty, w, 30 + 21 * len(FRAMES) + 8, c["box"], c["line"])
    s.text(x + 10, ty + 18, "card frame, sponza 1,024 x 1,024", 12, bold=True)
    for i, (preset, ms) in enumerate(FRAMES):
        ry = ty + 40 + 21 * i
        s.text(x + 10, ry, preset, 12.5, c["a"][0], mono=True)
        s.text(x + w - 10, ry, ms + " ms", 12.5, c["r"][0], True, anchor="end")
    return ty + 30 + 21 * len(FRAMES) + 8


def figure_teaser(theme):
    w, h = 1280, 500
    s = Svg(
        theme,
        "Komorebi-Prism: the host sends a camera and one FRAME command, the card runs "
        "the preset's stages by itself, the picture comes back",
        w,
    )
    c = s.c
    lx, lw = 16, 300
    mx, mw = 336, 620
    rx, rw = 976, 288
    s.text(lx, 36, "the host sends", 22, bold=True)
    s.text(mx, 36, "the card runs it by itself", 22, c["a"][0], True)
    s.text(rx, 36, "what comes back", 22, bold=True)
    top = 56
    teaser_host(s, lx, top, lw)
    teaser_card(s, mx, top, mw, h - top - 16)
    teaser_out(s, rx, top, rw, theme)
    s.line(lx + lw + 4, top + 140, mx - 4, top + 140, "w", 2.2)
    s.line(mx + mw + 4, top + 140, rx - 4, top + 140, "b", 2.2)
    s.text(rx, h - 44, "display.picture: the frame's pages,", 11.5, c["mute"])
    s.text(rx, h - 28, "pushed by the card into the host's memory", 11.5, c["mute"])
    s.text(
        rx,
        h - 12,
        "Sponza CC BY 3.0; Bistro CC BY 4.0 (credits below)",
        10.5,
        c["mute"],
    )
    return s.finish(h)


# ---------------------------------------------------------------------------
# The frame: the stages in order with their slots; the sun's commands.
# ---------------------------------------------------------------------------

COLUMNS = [
    (
        "raster",
        "layer unit: each layer",
        ["COUNT SUM HIST HSUM", "middle (on the thread)", "PLACE SETUP FILL"],
        ["scene.mesh", "view.camera"],
        ["frame.visibility", "frame.lists"],
    ),
    (
        "material.texture",
        "layer unit: each layer",
        ["SHADE", "opaque; masked merged;", "glass blended over"],
        ["frame.visibility", "frame.lists"],
        ["mesh.attributes", "frame.surface"],
    ),
    (
        "direct.light",
        "frame unit: the view",
        ["LIGHT", "displayed, or linear", "then glass"],
        ["frame.visibility", "mesh.attributes", "frame.surface", "light.shadow_map"],
        ["frame.visibility"],
    ),
    (
        "post.show",
        "frame unit: the view",
        ["SHOW: 8-bit pixels,", "a page a tile;", "then PUSH"],
        ["frame.visibility"],
        ["display.picture"],
    ),
]
LAYERS = ("opaque", "masked", "glass")


def frame_panel(s, y):
    c = s.c
    cw, gap = 180, 26
    x0 = BOX_X + 14
    sy = y + 38
    ty = sy + 54
    by = ty + 40
    wy = by + 3 * 32 + 14
    ry = wy + 62
    wy2 = ry + 20 + 21 * 4 + 6
    height = wy2 + 20 + 21 + 14 - y
    panel_frame(
        s,
        y,
        height,
        "a FRAME command: the eye's view, COLOUR",
        "prism/program/director: dr_view",
        "a",
    )
    s.rect(BOX_X + 14, sy, BOX_W - 28, 26, c["bg"], c["w"][0], rx=3, sw=1.4)
    s.text(BOX_X + 26, sy + 17, "director (X280 cluster 1)", 12, c["w"][0], True)
    s.text(
        BOX_X + BOX_W - 26,
        sy + 17,
        "each unit in the preset's order; a layer unit once a layer",
        12,
        c["mute"],
        anchor="end",
    )
    for k, (name, role, work, reads, writes) in enumerate(COLUMNS):
        cx = x0 + k * (cw + gap)
        s.line(cx + cw / 2, sy + 28, cx + cw / 2, ty - 3, "w", 1.6)
        s.text(cx, ty + 12, name, 12.5, c["fg"], True, mono=True)
        s.text(cx, ty + 30, role, 11.5, c["mute"])
        if "layer" in role:
            label = "COUNT ... FILL" if k == 0 else "SHADE"
            for i, layer in enumerate(LAYERS):
                ly = by + 32 * i
                s.rect(cx, ly, cw, 26, c["a"][1], c["a"][0], rx=3)
                s.text(cx + 8, ly + 17, layer, 12, c["fg"], True)
                s.text(cx + cw - 8, ly + 17, label, 11.5, anchor="end")
            for i, line in enumerate(work):
                s.text(cx, wy + 4 + 16 * i, line, 11.5, c["mute"])
        else:
            colour = "p" if k == 2 else "b"
            s.rect(cx, by, cw, 90, c[colour][1], c[colour][0], rx=3)
            for i, line in enumerate(work):
                s.text(cx + 8, by + 22 + 20 * i, line, 12, c["fg"], i == 0)
        s.text(cx, ry, "reads", 11.5, c["mute"], True)
        for i, slot in enumerate(reads):
            s.slot(cx, ry + 20 + 21 * i, slot)
        s.text(cx, wy2, "writes", 11.5, c["mute"], True)
        for i, slot in enumerate(writes):
            s.slot(cx, wy2 + 20 + 21 * i, slot, "r")
        if k < len(COLUMNS) - 1:
            ay = by + 45
            s.line(cx + cw + 3, ay, cx + cw + gap - 3, ay, "a", 2.0)
    return height


def sun_panel(s, y):
    c = s.c
    names = ["host", "director", "Tensix cores"]
    lanes = Lanes(s, y + 76, names, BOX_X + 112, BOX_X + BOX_W - 20, pitch=34)
    end = lanes.axis()
    notes = [
        (
            "sun (direct.shadow_pcf): a DEPTH view a quadrant of the map, through the "
            "same units: the opaque"
        ),
        (
            "and masked layers' raster, SHADE's masked merge of 1/z, then COPY of 1/z "
            "into light.shadow_map."
        ),
        (
            "update (indirect.field_update, in gi): the sources from light.shadow_map, a "
            "bounce pass an apply of"
        ),
        (
            "indirect.transport (elements.radiance in, elements.irradiance out), the "
            "field's pages into light.field;"
        ),
        (
            "field_scale gives light.field_scale to the host, which writes LIGHT's table. "
            "Then the next FRAME."
        ),
    ]
    height = end + 18 + 18 * len(notes) + 6 - y
    panel_frame(
        s,
        y,
        height,
        "when the sun moves: thread commands of their own, before the next FRAME",
        "",
        "m",
    )
    lead = "they write"
    s.text(BOX_X + 14, y + 46, lead, 12, c["mute"])
    right = s.slot(BOX_X + 14 + width(lead) + 6, y + 46, "light.shadow_map", "r")
    s.text(right + 8, y + 46, "and", 12, c["mute"])
    right = s.slot(right + 38, y + 46, "light.field", "r")
    s.text(right + 8, y + 46, "which the next frames read", 12, c["mute"])
    host, thread, cores = names
    lanes.bar(host, 0, 5, "", "w")
    s.text(lanes.tx(0), lanes.top[host] - 6, "control: sun", 12, c["w"][0], True)
    for q in range(4):
        t = 6 + 8.6 * q
        lanes.bar(thread, t, t + 1.4, "", "m")
        lanes.hop(thread, cores, t + 0.7, "a", sw=1.4)
        lanes.bar(cores, t + 1.2, t + 8.4, f"view {q + 1}", "m")
    lanes.hop(host, thread, 5.6, "w")
    s.text(lanes.tx(7.4), lanes.top[thread] - 6, "sun", 12, c["m"][0], True)
    lanes.hop(host, thread, 41.6, "w")
    lanes.bar(thread, 42, 50.5, "sources", "p")
    s.text(lanes.tx(43), lanes.top[thread] - 6, "update", 12, c["p"][0], True)
    for k, a in enumerate((51, 61)):
        lanes.hop(thread, cores, a + 0.3, "a", sw=1.4)
        lanes.bar(cores, a + 0.6, a + 8.2, "apply", "y")
        lanes.bar(thread, a + 8.4, a + 9.8, "", "p")
    lanes.bar(thread, 71.2, 79, "finish", "p")
    lanes.bar(thread, 79.6, 81, "", "g")
    lanes.hop(thread, host, 80.3, "g", sw=1.4)
    lanes.bar(host, 81.2, 88.4, "scale", "g")
    s.text(lanes.tx(78), lanes.top[host] - 6, "field_scale", 12, c["mute"], True)
    lanes.hop(host, thread, 89.2, "w")
    lanes.bar(thread, 89.6, 99.8, "FRAME", "w")
    lanes.bar(cores, 90.6, 99.8, "frame", "a")
    for i, line in enumerate(notes):
        s.text(BOX_X + 14, end + 20 + 18 * i, line, 12, c["mute"])
    return height


def figure_frame(theme):
    s = Svg(theme, "A frame in time, and the sun's commands outside it", 830)
    y = 10
    y += frame_panel(s, y) + 10
    y += sun_panel(s, y) + 10
    items = [
        ("bar:a", "a layer's work on the cores"),
        ("bar:p", "LIGHT"),
        ("bar:b", "SHOW and PUSH"),
        ("slot:y", "a slot read"),
        ("slot:r", "a slot written"),
        ("w", "a command to the thread"),
        ("a", "commands to the cores"),
    ]
    note = (
        (
            "Every core runs every stage's handlers: one program. A DEPTH view runs the "
            "layers whose depth column is set,"
        ),
        (
            "and LIGHT does nothing in it. The slots are those of each implementation's "
            "declaration (src/prism/stages)."
        ),
    )
    end = key_row(s, BOX_X + 4, y + 2, BOX_X + BOX_W - 4, items, note)
    return s.finish(int(end + 8))


# ---------------------------------------------------------------------------
# Assembly: a preset into one program and one thread.
# ---------------------------------------------------------------------------

FOLDER = [
    ("__init__.py", "fills, reads, writes"),
    ("device.py", "Shade: its class"),
    ("kernels/", "its C++"),
    ("thread/", "its unit's C"),
    ("unit.py", "what the unit asks for"),
    ("host.py", "TextureHost"),
    ("model/", "its data in numpy"),
    ("check/", "against prism_reference"),
    ("README.md", "its page"),
]
ASSIGNED = [
    ("km.merge", "handler numbers over the classes; their buffers in one layout"),
    (
        "prism.core.fields",
        "fields several classes share, each sized by its largest user;",
    ),
    ("", "command_space: each stage's parts over the same bytes"),
    (
        "prism.core.resources",
        "the thread's regions, numbers, layer columns, times, results,",
    ),
    ("", "the commands' numbers (FRAME is 1); refused with the numbers"),
    ("prism.core.capacity", "the tiles a load is sized for; a reload past them"),
]


def figure_assembly(theme):
    s = Svg(theme, "How a pipeline is put together: one program, one thread", 830)
    c = s.c
    y = 10
    top_h = 300
    # the preset
    px, pw = BOX_X, 206
    panel_frame(s, y, top_h, "a preset", "", "a", px, pw)
    s.text(px + 14, y + 42, "configs/pipeline/gi.py", 11.5, c["mute"])
    for i, name in enumerate(PRESETS["gi"]):
        ry = y + 66 + 26 * i
        has_class = DECLARED[name][1] is not None
        edge, fill, pale = c["a"]
        s.rect(px + 14, ry - 13, 12, 12, edge if has_class else pale, edge, rx=2)
        s.text(px + 34, ry - 2, name, 11.5, c["fg"], mono=True)
    for i, (text, fill) in enumerate((("a class", 0), ("a unit and a host", 2))):
        ly = y + top_h - 30 + 17 * i
        s.rect(px + 14, ly - 10, 12, 12, c["a"][fill], c["a"][0], rx=2)
        s.text(px + 34, ly, text, 11.5, c["mute"])
    # one implementation's folder
    fx, fw = px + pw + 22, 262
    panel_frame(s, y, top_h, "an implementation", "", "y", fx, fw)
    s.text(fx + 14, y + 42, "src/prism/stages/material/texture/", 11.5, c["mute"])
    for i, (name, what) in enumerate(FOLDER):
        ry = y + 66 + 25 * i
        s.text(fx + 14, ry, name, 12, c["fg"], True, mono=True)
        s.text(fx + 106, ry, what, 11.5, c["mute"])
    s.line(px + pw + 3, y + 150, fx - 3, y + 150, "a", 2.0)
    # the one program and the thread
    ox = fx + fw + 22
    ow = BOX_X + BOX_W - ox
    panel_frame(s, y, top_h, "one program", "", "r", ox, ow)
    s.line(fx + fw + 3, y + 150, ox - 3, y + 150, "a", 2.0)
    s.text(ox + 14, y + 44, "km.merge(Raster, Shade,", 12, c["fg"], mono=True)
    s.text(ox + 14, y + 62, "  Apply, Light, Show)", 12, c["fg"], mono=True)
    s.rect(ox + 14, y + 74, ow - 28, 84, c["a"][2], c["a"][0], rx=3)
    s.text(ox + 24, y + 94, "every Tensix core", 12.5, c["a"][0], True)
    s.text(ox + 24, y + 113, "the classes' handlers, merged;", 12)
    s.text(ox + 24, y + 131, "one compute set: HiFi4,", 12)
    s.text(ox + 24, y + 147, "float32 in Dst", 12)
    s.rect(ox + 14, y + 168, ow - 28, 118, c["w"][2], c["w"][0], rx=3)
    s.text(ox + 24, y + 188, "the thread, X280 cluster 1", 12.5, c["w"][0], True)
    thread = [
        ("director.c", "the runtime"),
        ("pipeline.c", "generated sequence"),
        ("<unit>_unit.c", "each unit's C"),
    ]
    for i, (name, what) in enumerate(thread):
        ry = y + 210 + 19 * i
        s.text(ox + 24, ry, name, 11.5, c["fg"], mono=True)
        s.text(ox + 124, ry, what, 11.5, c["mute"])
    s.text(ox + 24, y + 274, "the sequence: dr_view, kmx_program", 11.5, c["mute"])
    # what the core assigns
    ay = y + top_h + 10
    ah = 48 + 20 * len(ASSIGNED) + 26
    panel_frame(
        s,
        ay,
        ah,
        "implementations ask; the core assigns",
        "no number written by hand",
        "w",
    )
    for i, (who, what) in enumerate(ASSIGNED):
        ry = ay + 50 + 20 * i
        if who:
            s.text(BOX_X + 14, ry, who, 12, c["w"][0], mono=True)
        s.text(BOX_X + 190, ry, what, 12)
    s.text(
        BOX_X + 14,
        ay + ah - 12,
        "A slot is passed by its name: a unit gives or takes it on the thread, a host "
        "gives it (slots()) or connects to it.",
        11.5,
        c["mute"],
    )
    return s.finish(int(ay + ah + 10))


# ---------------------------------------------------------------------------
# Light: what a pixel adds, and the indirect field.
# ---------------------------------------------------------------------------

TERMS = [
    ("sun", "x the shadow map's taps (PCF)", "light.shadow_map", "m"),
    ("lamps", "the scene's point lights", None, "y"),
    ("specular", "of the sun and the lamps", None, "y"),
    ("sky", "x baked visibility", None, "b"),
    ("ambient", "a constant", None, "g"),
    ("emissive", "the material's own", None, "y"),
    ("background", "the sky's map where no surface", None, "b"),
]


def figure_light(theme):
    s = Svg(theme, "Where the light of a pixel comes from", 830)
    c = s.c
    y = 10
    h = 480
    lw = 396
    panel_frame(s, y, h, "LIGHT: a pixel's terms", "direct.light", "p", BOX_X, lw)
    for i, (name, what, slot, colour) in enumerate(TERMS):
        ry = y + 46 + 40 * i
        edge, fill, _ = c[colour]
        s.rect(BOX_X + 14, ry, 92, 28, fill, edge, rx=3)
        s.text(BOX_X + 60, ry + 19, name, 12, c["fg"], True, anchor="middle")
        s.text(BOX_X + 116, ry + 13, what, 11.5, c["mute"])
        if slot:
            s.slot(BOX_X + 116, ry + 31, slot, "m")
    # the field replaces sky x visibility and ambient
    fy = y + 46 + 40 * 3 - 4
    s.rect(BOX_X + 8, fy, lw - 16, 76, "none", c["p"][0], rx=4, sw=1.6, dash="5 3")
    s.text(
        BOX_X + lw - 18,
        fy + 22,
        "with the term indirect:",
        11.5,
        c["p"][0],
        True,
        anchor="end",
    )
    s.text(
        BOX_X + lw - 18,
        fy + 39,
        "the field I(P, n) instead",
        11.5,
        c["p"][0],
        True,
        anchor="end",
    )
    s.slot(BOX_X + lw - 18, fy + 62, "light.field", "p", anchor="end")
    ty = y + 46 + 40 * len(TERMS) + 6
    s.rect(BOX_X + 14, ty, lw - 28, 28, c["p"][1], c["p"][0], rx=3)
    s.text(
        BOX_X + 24,
        ty + 19,
        "the tone step: exposure, saturation, curve",
        12,
        c["fg"],
        True,
    )
    s.line(BOX_X + lw / 2, ty + 30, BOX_X + lw / 2, ty + 48, "p", 1.8)
    s.slot(BOX_X + lw / 2, ty + 62, "frame.visibility", "r", anchor="middle")
    # the field, updated on the card
    rx_ = BOX_X + lw + 12
    rw = BOX_X + BOX_W - rx_
    panel_frame(s, y, h, "the indirect field", "indirect.field_update", "p", rx_, rw)
    steps = [
        ("elements", "points sampled by area; sponza 36,832", None),
        ("L0", "each element's sun (shadow map), lamps, sky", "light.shadow_map"),
        (
            "E1 = M L0",
            "a bounce pass: indirect.transport's apply",
            "elements.irradiance",
        ),
        ("Ek = M (albedo/pi E(k-1))", "the next passes; bounces, default 2", None),
        ("the field", "voxels x 6 directions: E + the sky", None),
        ("texels, pages", "a has-data bit, three square-root codes", "light.field"),
    ]
    for i, (name, what, slot) in enumerate(steps):
        ry = y + 46 + 66 * i
        s.rect(rx_ + 14, ry, rw - 28, 50, c["box"] if i else c["cell"], c["p"][0], rx=3)
        s.text(rx_ + 24, ry + 19, name, 12, c["fg"], True, mono=True)
        s.text(rx_ + 24, ry + 38, what, 11.5, c["mute"])
        if slot:
            s.slot(rx_ + rw - 22, ry + 19, slot, "y" if i < 5 else "p", anchor="end")
        if i < len(steps) - 1:
            s.line(rx_ + rw / 2, ry + 52, rx_ + rw / 2, ry + 64, "p", 1.6)
    s.text(
        rx_ + 14,
        y + h - 30,
        "M: the transport matrix, hierarchical, applied as y = M x",
        11.5,
        c["mute"],
    )
    s.text(
        rx_ + 14,
        y + h - 13,
        "on every core (x: elements.radiance). Sent when the sun moves.",
        11.5,
        c["mute"],
    )
    py = y + 46 + 66 * 5 + 25
    s.poly([(rx_ + 12, py), (BOX_X + lw - 6, py), (BOX_X + lw - 6, fy + 78)], "p", 1.8)
    return s.finish(y + h + 10)


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "docs" / "images"
    out.mkdir(parents=True, exist_ok=True)
    figures = {
        "teaser": figure_teaser,
        "frame": figure_frame,
        "assembly": figure_assembly,
        "light": figure_light,
    }
    for theme in THEMES:
        for name, draw in figures.items():
            (out / f"{name}-{theme}.svg").write_text(draw(theme) + "\n")


if __name__ == "__main__":
    main()
