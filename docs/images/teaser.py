"""Draws the README's first figure, docs/images/teaser-{light,dark}.svg: what one gives
the renderer, the card drawing by itself, what comes out.

usage: python docs/images/teaser.py [output folder]    (needs Pillow, for the four
pictures)

Left, cards of real lines (teaser_lines.py), each marked in the colour of the mark the
centre draws for it; the shell commands of docs/guides/quick_start.md wrapped at their
arguments, the C lines without their indentation. Centre: the card as levels.py draws it
(ports: X280 1; the job thread: clusters 2 and 3, program/jobs/thread.py; an update's
applies on ranks 0 to 29, update_cores 30); one frame's phases and the update after a
sun move from measurements/gi_threads (Sponza). Right: frames of gi_threads from the
viewer (docs/images/frame-*.jpg), triangles from docs/concepts/scenes.md, ms from
measurements/gi_threads; the rows from measurements/gi_threads (frame ratio less push,
lynxsdesign_a01894bbb8, the update), docs/internals/raster/model.md (lists grown,
checks/camera_moves), measurements/transport_build (the artists' scene, 8 threads) and
measurements/account with threads_account (lit, Sponza: FILL, SHADE, LIGHT written
against the rows out), as resident.py quotes them.
"""

import base64
import io
import sys

from draw import REPO, Svg, write
from PIL import Image
from teaser_lines import (
    CARDS,
    FRAME_MS,
    FRAMES_DURING,
    GI_LESS_PUSH_MS,
    GI_STOP_MS,
    NOTES,
    PHASES,
    PICTURES,
    RATIOS,
    ROWS,
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
            apply = rank < 30
            s.rect(
                px,
                ry,
                cell,
                cell,
                c["r"][1],
                c["a"][0] if apply else c["r"][0],
                rx=2,
                sw=1.6 if apply else 0.6,
                layer=0,
            )
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
    # the job thread queues the applies on ranks 0 to 29
    w2 = mid["X280 2"]
    s.line(xc - 1, w2, at[26][0] + 5, at[26][1] + 5, "m", 1.6)
    s.line(xc + bw + 1, w2, at[21][0] - 5, at[21][1] + 5, "m", 1.6)
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
        ("a", "ranks 0 to 29: an update's applies"),
        ("m", "X280 2, 3: the job thread's graph"),
        ("p", "the display pages leave"),
    )
    for i, (colour, text) in enumerate(items):
        ly = y + i * 15
        if colour == "r":
            s.rect(x + 4, ly - 9, 12, 12, c["r"][1], c["r"][0], rx=2, sw=0.6)
        elif colour == "a":
            s.rect(x + 4, ly - 9, 12, 12, c["r"][1], c["a"][0], rx=2, sw=1.6)
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
    """One gi_threads frame's phases and gi less push; returns the bottom."""
    c = s.c
    s.text(x, y, "one gi_threads frame, Sponza", 12, c["fg"], True)
    s.text(x + w, y, f"{FRAME_MS:.2f} ms", 12, c["r"][0], True, anchor="end")
    label = 58
    x0, span = x + label, w - label - 2
    scale = (span - 40) / GI_LESS_PUSH_MS
    rows = ("host", "X280 1", "cores")
    ys = [y + 10 + 22 * i for i in range(3)]
    for name, ly in zip(rows, ys, strict=True):
        s.text(x, ly + 13, name, 11, c["fg"], True)
        s.rule(x0, ly + 9, x + w, ly + 9, 0.6)
    s.rect(x0 + 4, ys[0] + 2, 170, 15, c["bg"], rx=2)
    s.text(x0 + 6, ys[0] + 13, "FRAME: no round trip", 11, c["mute"])
    s.rect(x0, ys[1], FRAME_MS * scale, 18, c["w"][2], c["w"][0], rx=2, sw=1)
    s.text(x0 + 6, ys[1] + 13, "answers the pulls", 11, c["fg"])
    t = 0.0
    for name, ms in PHASES:
        colour = c["r"][0] if name == "tile" else c["r"][1]
        s.rect(
            x0 + t * scale + 0.4, ys[2], max(ms * scale - 0.8, 1.2), 18, colour, rx=1
        )
        t += ms
    tx = x0 + (t - PHASES[-1][1] / 2) * scale
    label = f"tile {PHASES[-1][1]:.2f}"
    s.text(tx, ys[2] + 13, label, 11, c["ink"], True, anchor="middle")
    first = ", ".join(f"{n} {ms:.2f}" for n, ms in PHASES[:3])
    s.text(x0, ys[2] + 32, first, 11, c["mute"])
    by = ys[2] + 42
    s.text(x, by + 13, "gi", 11, c["fg"], True)
    s.rect(x0, by, GI_LESS_PUSH_MS * scale, 18, c["g"][1], c["rule"], rx=2, sw=0.8)
    s.text(x0 + 6, by + 13, "stage-wise, less push", 11, c["fg"])
    s.text(x + w, by + 13, f"{GI_LESS_PUSH_MS:.2f}", 11, c["fg"], True, anchor="end")
    return by + 18


def update(s, x, y, w):
    """The field's update after a sun move, in each form; returns the bottom."""
    c = s.c
    s.text(x, y, "the sun moved: the field's update", 12, c["fg"], True)
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
    """Each scene's frame over gi's less push as a dot on 0.6 to 1.1; returns the
    bottom."""
    c = s.c
    s.text(x, y, "every scene: gi_threads / gi less push", 12, c["fg"], True)
    label, low, high = 124, 0.6, 1.1
    x0, span = x + label, w - label - 30

    def at(r):
        return x0 + (r - low) / (high - low) * span

    top = y + 8
    for i, (name, ratio) in enumerate(RATIOS):
        ry = top + 14 * i
        s.text(x, ry + 10.5, name, 11, c["fg"], mono=" " not in name)
        s.rule(x0, ry + 7, x0 + span, ry + 7, 0.5, "1 3")
        colour = "p" if ratio > 1 else "r"
        s.rect(at(ratio) - 4, ry + 3, 8, 8, c[colour][0], rx=4)
        s.text(x0 + span + 4, ry + 10.5, f"{ratio:.2f}", 11, c[colour][0], True)
    bottom = top + 14 * len(RATIOS)
    s.rule(at(1.0), top - 2, at(1.0), bottom + 2, 1.2)
    for r in (0.6, 0.8, 1.0):
        s.text(at(r), bottom + 12, f"{r:.1f}", 11, c["mute"], anchor="middle")
    return bottom + 12


def jpeg_uri(path, middle):
    """A picture cut to PW x PH around `middle` (of its height), at twice the size."""
    image = Image.open(path).convert("RGB")
    side = image.width
    h = round(side * PH / PW)
    top = min(max(round(middle * side - h / 2), 0), side - h)
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
        s.rect(x, y, RW, 44, c["box"], c["line"], rx=4, layer=0)
        s.text(x + 7, y + 14, what, 11, c["fg"], True)
        s.text(x + RW - 7, y + 14, condition, 11, c["mute"], anchor="end")
        s.text(x + 7, y + 27, value, 11.5, c[colour][0], True)
        s.text(x + 7, y + 40, against, 11, c["mute"])
        y += 48
    return y - 4


def teaser(theme):
    s = Svg(theme, "Komorebi-Prism: what one gives it, the card drawing alone", FW)
    c = s.c
    s.text(LX, 22, "you give it", 17, c["fg"], True)
    s.text(MX, 22, "the card draws it by itself", 17, c["w"][0], True)
    s.text(RX, 22, "what comes out", 17, c["fg"], True)

    y = TOP
    for spec in CARDS:
        y = card(s, LX, y, LW, *spec) + 5
    left = y - 5
    s.line(LX + LW + 1, 300, MX - 3, 300, "g", 1.8)

    s.rect(MX, TOP, MW, left - TOP, c["bg"], c["w"][0], rx=6, sw=1.6, layer=0)
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
    ratios(s, ix, uy, iw)

    right = outcomes(s, RX, TOP)
    ny = max(left, right) + 16
    for i, note in enumerate(NOTES):
        s.text(LX, ny + 14 * i, note, 11, c["mute"])
    return s.finish(ny + 14 * len(NOTES) - 4)


def main():
    write({"teaser": teaser}, sys.argv[1] if len(sys.argv) > 1 else None)


if __name__ == "__main__":
    main()
