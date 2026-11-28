"""Draws docs/images/pipeline-{light,dark}.svg: the renderer's items, the slots that pass
between them, the step each gives the tile thread, and which implementation fills each
item in each preset, in the threads' form and in the stage-wise form.

usage: python docs/images/pipeline.py [output folder]    (the standard library only)

Names: the items and slots of docs/concepts/renderer.md and src/prism_common/slots.py,
the implementations' declarations (program/threads/implementations.py), the steps of
program/threads/tiles.py, the presets of configs/pipeline.
"""

import sys

from draw import Svg, chip, width, write

FW = 880

ITEMS = ("raster", "material", "shadow", "direct", "indirect", "post")
PRESETS = (
    (
        "textured_threads",
        "threads",
        ("raster.threads", "material.texture.threads", "", "", "", "post.show.threads"),
    ),
    (
        "lit_threads",
        "threads",
        (
            "raster.threads",
            "material.texture.threads",
            "direct.shadow_pcf",
            "direct.light.threads",
            "",
            "post.show.threads",
        ),
    ),
    (
        "gi_threads",
        "threads",
        (
            "raster.threads",
            "material.texture.threads",
            "direct.shadow_pcf",
            "direct.light.threads_field",
            "indirect.transport.threads|indirect.field_update.threads",
            "post.show.threads",
        ),
    ),
    ("textured", "stage-wise", ("raster", "material.texture", "", "", "", "post.show")),
    (
        "lit",
        "stage-wise",
        (
            "raster",
            "material.texture",
            "direct.shadow_pcf",
            "direct.light",
            "",
            "post.show",
        ),
    ),
    (
        "gi",
        "stage-wise",
        (
            "raster",
            "material.texture",
            "direct.shadow_pcf",
            "direct.light",
            "indirect.transport|indirect.field_update",
            "post.show",
        ),
    ),
)


def stage_box(s, x, y, w, h, item, what, step, colour):
    c = s.c
    s.rect(x, y, w, h, c[colour][2], c[colour][0], rx=6, sw=1.4)
    s.text(x + 10, y + 18, item, 13, c[colour][0], True)
    s.text(x + 10, y + 34, what, 11, c["fg"])
    if step:
        chip(s, x + 8, y + h - 30, w - 16, 22, step, "r", size=11.5)


def flow(s, top):
    """The items and the slots between them; returns the bottom."""
    c = s.c
    s.text(
        16,
        top + 18,
        "the items, the slots between them, the step each gives " "the tile thread",
        14,
        c["fg"],
        True,
    )
    y, h = top + 92, 86
    xs = {"raster": 16, "material": 276, "direct": 546, "post": 740}
    ws = {"raster": 120, "material": 130, "direct": 110, "post": 124}
    stage_box(
        s,
        xs["raster"],
        y,
        ws["raster"],
        h,
        "raster",
        "the layers' visibility",
        "visibility",
        "w",
    )
    stage_box(
        s,
        xs["material"],
        y,
        ws["material"],
        h,
        "material",
        "texels; lit surfaces",
        "material_lit",
        "a",
    )
    stage_box(
        s, xs["direct"], y, ws["direct"], h, "direct", "sun, lamps, sky", "light", "y"
    )
    stage_box(
        s, xs["post"], y, ws["post"], h, "post", "8-bit, a page a tile", "post", "p"
    )
    # inputs
    s.slot(24, top + 46, "scene.mesh", "g")
    s.slot(24, top + 68, "view.camera", "g")
    s.line(70, top + 76, 70, y - 2, "g", 1.6)
    # raster -> material
    x1, x2 = xs["raster"] + ws["raster"], xs["material"]
    s.line(x1 + 2, y + 40, x2 - 2, y + 40, "w", 1.8)
    s.slot((x1 + x2) / 2, y + 26, "frame.visibility", "y", "middle")
    s.slot((x1 + x2) / 2, y + 64, "frame.lists", "w", "middle")
    # material -> direct
    x1, x2 = xs["material"] + ws["material"], xs["direct"]
    s.line(x1 + 2, y + 40, x2 - 2, y + 40, "a", 1.8)
    s.slot((x1 + x2) / 2, y + 26, "frame.surface", "y", "middle")
    s.slot((x1 + x2) / 2, y + 64, "mesh.attributes", "a", "middle")
    # direct -> post
    x1, x2 = xs["direct"] + ws["direct"], xs["post"]
    s.line(x1 + 2, y + 40, x2 - 2, y + 40, "y", 1.8)
    s.text((x1 + x2) / 2, y + 30, "colour", 11, c["mute"], anchor="middle")
    s.text((x1 + x2) / 2, y + 60, "planes", 11, c["mute"], anchor="middle")
    s.slot(FW - 16, y + h + 22, "display.picture", "p", "end")
    s.line(xs["post"] + 70, y + h + 2, xs["post"] + 70, y + h + 8, "p", 1.6)
    # shadow above direct
    sx, sy, sw = 476, top + 26, 254
    s.rect(sx, sy, sw, 40, c["box"], c["rule"], rx=6, sw=1.2, dash="5 3")
    s.text(sx + 10, sy + 16, "shadow: the sun's DEPTH views", 12, c["fg"], True)
    s.text(
        sx + 10,
        sy + 32,
        "visibility, material_lit, depth_out",
        11,
        c["mute"],
        mono=True,
    )
    s.line(sx + 124, sy + 42, sx + 124, y - 2, "g", 1.6)
    s.slot(sx + 130, sy + 58, "light.shadow_map", "g")
    # indirect below direct
    iy = y + h + 40
    s.rect(sx - 10, iy, 260, 52, c["m"][2], c["m"][0], rx=6, sw=1.2)
    s.text(sx, iy + 17, "indirect: the field", 12, c["m"][0], True)
    s.text(sx, iy + 33, "the transport's apply a bounce;", 11, c["fg"])
    s.text(sx, iy + 46, "the job thread, beside the frames", 11, c["fg"])
    s.line(xs["direct"] + 40, iy - 2, xs["direct"] + 40, y + h + 2, "m", 1.6)
    s.slot(xs["direct"] + 48, iy - 14, "light.field", "m")
    s.slot(sx - 10, iy + 70, "elements.radiance", "m")
    s.slot(sx + 126, iy + 70, "elements.irradiance", "m")
    # the tile thread brace
    ty = iy + 6
    s.text(16, ty + 4, "the tile thread LIT: one core runs", 11.5, c["r"][0], True)
    s.text(16, ty + 19, "the green steps of a tile in order;", 11.5, c["r"][0], True)
    s.text(16, ty + 34, "the yellow slots are planes in its L1", 11.5, c["r"][0], True)
    return iy + 84


def split(name, w):
    """`name` on one line, or two (broken before its last dot) when wider than w."""
    if width(name, 11, mono=True) <= w or "." not in name:
        return [name]
    head, tail = name.rsplit(".", 1)
    return [head, "." + tail]


def matrix(s, top):
    """Which implementation fills each item in each preset; returns the bottom."""
    c = s.c
    s.text(
        16,
        top + 18,
        "the presets: which implementation fills each item",
        14,
        c["fg"],
        True,
    )
    cols = (
        ("preset", 128),
        ("raster", 100),
        ("material", 126),
        ("shadow", 124),
        ("direct", 124),
        ("indirect", 142),
        ("post", 104),
    )
    x0, y = 16, top + 30
    xs = []
    x = x0
    for name, w in cols:
        xs.append((x, w))
        s.text(x + 6, y + 14, name, 12, c["mute"], True)
        x += w
    y += 22
    rh = 36
    for i, (preset, form, cells) in enumerate(PRESETS):
        ry = y + i * rh + (10 if i >= 3 else 0)
        colour = "r" if form == "threads" else "g"
        s.rect(
            x0,
            ry,
            x - x0,
            rh - 4,
            c[colour][2],
            c[colour][0] if i in (0, 3) else c[colour][2],
            rx=4,
            sw=0.8,
        )
        s.text(x0 + 6, ry + 14, preset, 12, c["fg"], True, mono=True)
        s.text(x0 + 6, ry + 27, form, 11, c["mute"])
        for (cx, w), cell in zip(xs[1:], cells, strict=True):
            if not cell:
                s.text(cx + w / 2, ry + 20, "-", 11, c["mute"], anchor="middle")
                continue
            parts = [p for name in cell.split("|") for p in split(name, w - 8)]
            if len(parts) > 2:
                parts = [n.replace("indirect.", "") for n in cell.split("|")]
            for k, part in enumerate(parts):
                yy = ry + (20 if len(parts) == 1 else 13 + 13 * k)
                s.text(cx + 4, yy, part, 11, c["fg"], mono=True)
    bottom = y + len(PRESETS) * rh + 22
    s.text(
        16,
        bottom + 8,
        "A threads' preset is judged by its stage-wise preset "
        "(gi_threads by gi), picture for picture. On a scene without its far field,",
        11.5,
        c["mute"],
    )
    s.text(
        16,
        bottom + 23,
        "gi_threads lights with direct.light.threads and fills no "
        "indirect item (the preset's FAR_FIELD_ABSENT).",
        11.5,
        c["mute"],
    )
    s.text(
        16,
        bottom + 38,
        "gi_threads also names indirect.near_tile, which fills no item: the one-tile "
        "indirect product, a step of the tile thread with the option near_tile (off).",
        11.5,
        c["mute"],
    )
    return bottom + 45


def pipeline(theme):
    s = Svg(theme, "Komorebi-Prism's pipeline: items, slots, steps and presets", FW)
    bottom = flow(s, 0)
    bottom = matrix(s, bottom + 10)
    return s.finish(bottom + 8)


def main():
    write({"pipeline": pipeline}, sys.argv[1] if len(sys.argv) > 1 else None)


if __name__ == "__main__":
    main()
