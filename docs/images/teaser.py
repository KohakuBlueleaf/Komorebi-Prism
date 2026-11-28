"""Draws the README's first figure, docs/images/teaser-{light,dark}.svg: what one gives
the renderer, the card drawing by itself, what comes out.

usage: python docs/images/teaser.py [output folder]    (needs Pillow, for the four
pictures)

Left, cards of real lines (teaser_lines.py), each marked in the colour of the mark the
centre draws for it; the shell commands of docs/guides/quick_start.md wrapped at their
arguments, the C lines without their indentation. Centre: the card as levels.py draws it
(ports: X280 1; the job thread: clusters 2 and 3, program/jobs/thread.py; an update's
applies as core steps on every core between two frames); one frame moving and standing
and the update after a sun move from measurements/gi_threads (Sponza). Right: frames of
gi_threads from the viewer (docs/images/frame-*.jpg; Italian Flat's at the camera of
measurements/gltf_truth), triangles from docs/concepts/scenes.md, ms from
measurements/gi_threads; the rows from measurements/gi_threads (the largest scene,
3,840 x 2,160, the update) and measurements/gltf_truth (Italian Flat, Cycles' time).
"""

import base64
import io
import sys

from draw import REPO, Svg, write
from PIL import Image
from teaser_lines import (
    BOUNCES,
    CARDS,
    FRAMES_DURING,
    GI_LESS_PUSH_MS,
    GI_STOP_MS,
    MOVES_MS,
    NOTES,
    PHASES,
    PICTURES,
    RATIOS,
    ROWS,
    STANDS_MS,
    SWAP_MS,
)

FW = 880
LX, LW = 8, 408  # the columns: left, centre, right
MX, MW = 426, 276
RX, RW = 712, 160
TOP = 34
STEP, HEAD = 14, 24  # a code line; a card's title row
PW, PH = 160, 92  # a picture


def pale(c, colour):
    return c[colour][1] if colour == "g" else c[colour][2]


def mark(s, x, y, colour, kind, length=20):
    s.line(
        x,
        y,
        x + length,
        y,
        colour,
        2.0,
        dash="4 3" if kind == "dash" else None,
        tail=kind == "both",
    )


def card(s, x, y, w, title, colour, kind, source, lines):
    """A card of real lines; returns its bottom."""
    c = s.c
    h = HEAD + STEP * len(lines) + 6
    s.rect(x, y, w, h, c["box"], c["line"], rx=4, layer=0)
    mark(s, x + 8, y + 12, colour, kind)
    s.text(x + 34, y + 16.5, title, 12, c["fg"], True)
    s.text(x + w - 8, y + 16.5, source, 11, c["mute"], anchor="end")
    for i, (text, tint, note, ink) in enumerate(lines):
        ly = y + HEAD + STEP * i
        if tint and tint != "skip":
            s.rect(x + 1, ly, w - 2, STEP, pale(c, tint), rx=0)
            s.rect(x + 1, ly, 3, STEP, c[tint][0], rx=0)
        fill = c["mute"] if tint == "skip" else c["fg"]
        s.text(x + 9, ly + 10.5, text, 11, fill, mono=True)
        if note:
            fill = c["mute"] if ink == "mute" else c[ink][0]
            s.text(x + w - 8, ly + 10.5, note, 11, fill, ink != "mute", anchor="end")
    return y + h


def grid(s, x, y):
    """The card: DRAM columns, 120 cores in two blocks, the X280 clusters, the marks;
    returns the bottom."""
    c = s.c
    pitch, cell, rows = 14, 12, 15
    bw = 60  # an X280 box
    dl, tl = x + 6, x + 17
    xc = tl + 6 * pitch + 5
    tr = xc + bw + 5
    dr = tr + 6 * pitch + 3
    at = {}
    for row in range(10):
        ry = y + row * rows
        for px in (dl, dr):
            s.rect(px, ry, 8, cell, c["dram"], rx=2, layer=0)
        for k in range(12):
            rank = row * 12 + k
            px = (tl if k < 6 else tr) + (k % 6) * pitch
            s.rect(px, ry, cell, cell, c["r"][1], c["r"][0], rx=2, sw=0.6, layer=0)
            at[rank] = (px + cell / 2, ry + cell / 2)
    boxes = (("X280 0", "g", "Komorebi"), ("X280 1", "w", "frame"))
    boxes += (("X280 2", "m", "jobs"), ("X280 3", "m", "jobs"))
    mid = {}
    for i, (name, colour, sub) in enumerate(boxes):
        by = y + i * 38
        s.rect(xc, by, bw, 33, c[colour][2], c[colour][0], rx=3, sw=1.4, layer=0)
        s.text(xc + bw / 2, by + 13, name, 11, c[colour][0], True, anchor="middle")
        s.text(xc + bw / 2, by + 27, sub, 11, c["fg"], anchor="middle")
        mid[name] = by + 16.5
    # pulls: cores and their port on X280 1, both ways
    w1 = mid["X280 1"]
    for rank in (39, 87):
        s.line(at[rank][0] + 6, at[rank][1], xc - 1, w1, "w", 1.6, tail=True)
    for rank in (44, 104):
        s.line(xc + bw + 1, w1, at[rank][0] - 6, at[rank][1], "w", 1.6, tail=True)
    # the display pages leave the card
    s.line(dr + 9, y + 75, RX - 4, y + 75, "p", 2.2)
    s.text(dr + 8, y + 162, "DRAM", 11, c["mute"], True, anchor="end")
    return y + 10 * rows


def key(s, x, y):
    """What each mark on the card is; returns the bottom."""
    c = s.c
    items = (
        ("w", "pulls: a core asks X280 1 for a thread"),
        ("r", "every core inside a tile thread"),
        ("a", "between two frames, every core: an apply"),
        ("m", "X280 2, 3: the job thread's graph"),
        ("p", "the display pages leave"),
    )
    for i, (colour, text) in enumerate(items):
        ly = y + i * 15
        if colour == "r":
            s.rect(x + 4, ly - 9, 12, 12, c["r"][1], c["r"][0], rx=2, sw=0.6)
        elif colour == "a":
            s.rect(x + 1, ly - 9, 7, 12, c["r"][1], c["r"][0], rx=2, sw=0.6)
            s.rect(x + 9, ly - 9, 3, 12, c["a"][1], c["a"][0], rx=1, sw=0.6)
            s.rect(x + 13, ly - 9, 7, 12, c["r"][1], c["r"][0], rx=2, sw=0.6)
        else:
            mark(s, x, ly - 3, colour, "both" if colour == "w" else "solid", 18)
        s.text(x + 26, ly, text, 11, c["fg"])
    return y + 5 * 15


def tile(s, x, y, w):
    """One core's tile thread: its steps, its planes in L1; returns the bottom."""
    c = s.c
    s.text(x, y, "the core that takes a tile runs, in order:", 11, c["fg"], True)
    px = x
    for name in ("visibility", "material_lit", "light", "post"):
        bw = len(name) * 6.62 + 10
        s.rect(px, y + 6, bw, 19, c["r"][2], c["r"][0], rx=4, sw=1.2)
        s.text(px + 5, y + 19.5, name, 11, c["fg"], mono=True)
        px += bw + 4
    s.rect(x, y + 30, w, 18, c["y"][2], c["y"][0], rx=4, sw=1.2)
    s.text(x + 6, y + 43, "frame.visibility, frame.surface: L1", 11, c["fg"], mono=True)
    s.text(x, y + 63, "in: lists, pages; out: one display page", 11, c["mute"])
    return y + 63


def frame(s, x, y, w):
    """One gi_threads frame moving and standing on one axis, gi less push under them;
    returns the bottom."""
    c = s.c
    s.text(x, y, "gi_threads, Sponza", 12, c["fg"], True)
    s.text(x + w, y, f"{STANDS_MS:.2f} ms standing", 12, c["r"][0], True, anchor="end")
    label = 58
    x0, span = x + label, w - label - 2
    scale = (span - 40) / GI_LESS_PUSH_MS
    my, sy, gy = y + 10, y + 50, y + 82
    s.text(x, my + 13, "moves", 11, c["fg"], True)
    t = 0.0
    for name, ms in PHASES:
        colour = c["r"][0] if name == "tile" else c["r"][1]
        s.rect(x0 + t * scale + 0.4, my, max(ms * scale - 0.8, 1.2), 18, colour, rx=1)
        t += ms
    s.text(x0 + t * scale + 4, my + 13, f"{MOVES_MS:.2f}", 11, c["fg"], True)
    s.text(x, sy + 13, "stands", 11, c["fg"], True)
    s.rect(x0, sy, STANDS_MS * scale, 18, c["r"][0], rx=1)
    s.text(x0 + 6, sy + 13, "the tile pull alone", 11, c["ink"], True)
    s.text(x0 + STANDS_MS * scale + 4, sy + 13, f"{STANDS_MS:.2f}", 11, c["fg"], True)
    first = ", ".join(f"{n} {ms:.2f}" for n, ms in PHASES[:3])
    s.text(x0, my + 32, f"{first}, tile", 11, c["mute"])
    s.text(x, gy + 13, "gi", 11, c["fg"], True)
    s.rect(x0, gy, GI_LESS_PUSH_MS * scale, 18, c["g"][1], c["rule"], rx=2, sw=0.8)
    s.text(x0 + 6, gy + 13, "stage-wise, less push", 11, c["fg"])
    s.text(x + w, gy + 13, f"{GI_LESS_PUSH_MS:.2f}", 11, c["fg"], True, anchor="end")
    return gy + 18


def update(s, x, y, w):
    """The field's update after a sun move, in each form; returns the bottom."""
    c = s.c
    s.text(x, y, f"sun moved: the field's update, {BOUNCES} bounces", 12, c["fg"], True)
    label = 72
    x0 = x + label
    scale = (w - label - 44) / GI_STOP_MS
    gy = y + 10
    s.text(x, gy + 13, "gi_threads", 11, c["fg"], True)
    s.rect(x0, gy, SWAP_MS * scale, 18, c["r"][2], c["m"][0], rx=2, sw=1.2)
    s.text(x0 + 6, gy + 13, f"{FRAMES_DURING} frames drawn", 11, c["fg"])
    s.rule(x0 + SWAP_MS * scale, gy - 3, x0 + SWAP_MS * scale, gy + 21, 2)
    s.text(x0 + SWAP_MS * scale + 4, gy + 13, f"{SWAP_MS}", 11, c["fg"], True)
    sy = gy + 24
    s.text(x, sy + 13, "gi", 11, c["fg"], True)
    s.rect(x0, sy, GI_STOP_MS * scale, 18, c["bg"], c["rule"], rx=2, sw=1, dash="4 3")
    s.text(x0 + 6, sy + 13, "stopped: no frame", 11, c["mute"])
    s.text(x0 + GI_STOP_MS * scale + 4, sy + 13, f"{GI_STOP_MS}", 11, c["fg"], True)
    s.text(x, sy + 34, "ms from the sun set to the new field's frame", 11, c["mute"])
    return sy + 34


def ratios(s, x, y, w):
    """Each scene's frame over gi's less push, standing (a dot) and moving (a ring), on
    0.3 to 1.0; returns the bottom."""
    c = s.c
    s.text(x, y, "every scene: gi_threads / gi less push", 12, c["fg"], True)
    label, low, high = 124, 0.3, 1.0
    x0, span = x + label, w - label - 30

    def at(r):
        return x0 + (r - low) / (high - low) * span

    top = y + 8
    for i, (name, stands, moves) in enumerate(RATIOS):
        ry = top + 14 * i
        s.text(x, ry + 10.5, name, 11, c["fg"], mono=True)
        s.rule(x0, ry + 7, x0 + span, ry + 7, 0.5, "1 3")
        s.rect(at(moves) - 4, ry + 3, 8, 8, c["bg"], c["r"][0], rx=4, sw=1.2)
        s.rect(at(stands) - 4, ry + 3, 8, 8, c["r"][0], rx=4)
        s.text(x0 + span + 4, ry + 10.5, f"{stands:.2f}", 11, c["r"][0], True)
    bottom = top + 14 * len(RATIOS)
    s.rule(at(1.0), top - 2, at(1.0), bottom + 2, 1.2)
    for r in (0.4, 0.6, 0.8, 1.0):
        s.text(at(r), bottom + 12, f"{r:.1f}", 11, c["mute"], anchor="middle")
    s.text(x, bottom + 26, "dot: standing; ring: moving", 11, c["mute"])
    return bottom + 26


def jpeg_uri(path, middle):
    """A picture cut to PW x PH around `middle` (of its height), at twice the size."""
    image = Image.open(path).convert("RGB")
    side = image.width
    h = round(side * PH / PW)
    top = min(max(round(middle * image.height - h / 2), 0), image.height - h)
    image = image.crop((0, top, side, top + h)).resize((2 * PW, 2 * PH), Image.LANCZOS)
    data = io.BytesIO()
    image.save(data, "JPEG", quality=72, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(data.getvalue()).decode()


def outcomes(s, x, y):
    """The pictures and the rows; returns the bottom."""
    c = s.c
    for stem, name, triangles, ms, middle in PICTURES:
        uri = jpeg_uri(REPO / "docs" / "images" / f"frame-{stem}.jpg", middle)
        s.add(f'<image x="{x}" y="{y}" width="{PW}" height="{PH}" href="{uri}"/>', 0)
        s.rect(x, y, PW, PH, "none", c["line"], rx=0, layer=0)
        s.text(x, y + PH + 13, name, 11, c["fg"], True)
        s.text(x, y + PH + 26, f"{triangles} tris, {ms:.2f} ms", 11, c["mute"])
        y += PH + 33
    for what, condition, value, against, colour in ROWS:
        h = 31 + 13 * len(against)
        s.rect(x, y, RW, h, c["box"], c["line"], rx=4, layer=0)
        s.text(x + 7, y + 14, what, 11, c["fg"], True)
        s.text(x + RW - 7, y + 14, condition, 11, c["mute"], anchor="end")
        s.text(x + 7, y + 27, value, 11.5, c[colour][0], True)
        for i, line in enumerate(against):
            s.text(x + 7, y + 40 + 13 * i, line, 11, c["mute"])
        y += h + 4
    return y - 4


def teaser(theme):
    s = Svg(theme, "Komorebi-Prism: what one gives it, the card drawing alone", FW)
    c = s.c
    s.text(LX, 22, "you give it", 17, c["fg"], True)
    s.text(MX, 22, "the card draws it by itself", 17, c["w"][0], True)
    s.text(RX, 22, "what comes out", 17, c["fg"], True)

    under = len(s.layers[0])  # the centre's frame goes under its cores
    ix, iw = MX + 10, MW - 20
    s.text(ix, TOP + 18, "host", 11, c["fg"], True)
    s.text(ix + 34, TOP + 18, "the camera and one command a frame", 11, c["mute"])
    s.rule(MX + 6, TOP + 26, MX + MW - 6, TOP + 26, 0.8)
    s.text(ix, TOP + 44, "P150A: 120 Tensix cores, 4 X280s", 11, c["fg"], True)
    gy = grid(s, MX, TOP + 54) + 22
    ky = key(s, ix, gy) + 10
    ty = tile(s, ix, ky, iw) + 22
    fy = frame(s, ix, ty, iw) + 26
    uy = update(s, ix, fy, iw) + 26
    centre = ratios(s, ix, uy, iw) + 10
    right = outcomes(s, RX, TOP)
    bottom = max(centre, right)
    s.rect(MX, TOP, MW, bottom - TOP, c["bg"], c["w"][0], rx=6, sw=1.6, layer=0)
    s.layers[0].insert(under, s.layers[0].pop())

    # the left cards spread to end level with the other two columns
    heights = sum(HEAD + STEP * len(spec[-1]) + 6 for spec in CARDS)
    gap = max(5, (bottom - TOP - heights) / (len(CARDS) - 1))
    y = TOP
    for spec in CARDS:
        y = card(s, LX, y, LW, *spec) + gap
    s.line(LX + LW + 1, 300, MX - 3, 300, "g", 1.8)
    ny = max(y - gap, bottom) + 16
    for i, note in enumerate(NOTES):
        s.text(LX, ny + 14 * i, note, 11, c["mute"])
    return s.finish(ny + 14 * len(NOTES) - 4)


def main():
    write({"teaser": teaser}, sys.argv[1] if len(sys.argv) > 1 else None)


if __name__ == "__main__":
    main()
