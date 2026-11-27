"""What the figures' generators share: the two themes' colours, the fonts and a
text's width, the SVG page (layers, shapes, text, arrows), a titled box and a chip, and
the writing of a figure's two files.

Standard library only. A generator imports it as a sibling: `import draw`.
"""

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


def write(figures, out=None):
    """Each figure of `figures` (name: a function of a theme's name giving the SVG) as
    <name>-<theme>.svg in `out` (docs/images when not given)."""
    out = Path(out) if out else REPO / "docs" / "images"
    out.mkdir(parents=True, exist_ok=True)
    for theme in THEMES:
        for name, figure in figures.items():
            (out / f"{name}-{theme}.svg").write_text(figure(theme) + "\n")
