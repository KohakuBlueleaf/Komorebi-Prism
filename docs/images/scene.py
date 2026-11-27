"""Draws docs/images/scene-{light,dark}.svg: a glTF file opened (what the importer reads,
the conversion into the data root, the hosts' tables and the tensors they write to the
card) and the far field built on the host afterwards, joined at the next load.

usage: python docs/images/scene.py [output folder]    (the standard library only)

Names are those of src/prism_reference/scene/importers/gltf/, apps/prism_cli/ and the
stages' hosts; the numbers are copied from measurements/open/README.md and
measurements/transport_build/README.md.
"""

import sys

from draw import Svg, chip, write

W = 830


def panel(s, y, h, title, colour, note=""):
    c = s.c
    s.rect(16, y, W - 32, h, c["box"], c["line"], layer=0)
    s.text(30, y + 22, title, 14, c[colour][0], True)
    if note:
        s.text(W - 30, y + 22, note, 12, c["mute"], anchor="end")


def column(s, x, y, w, h, title, sub, colour):
    c = s.c
    s.rect(x, y, w, h, c["bg"], c[colour][0], rx=6, sw=1.3, layer=0)
    s.text(x + 10, y + 19, title, 12.5, c[colour][0], True)
    s.text(x + 10, y + 35, sub, 11, c["mute"])


def lines(s, x, y, items, step=16, size=11.5):
    c = s.c
    for i, (text, mono) in enumerate(items):
        s.text(x, y + i * step, text, size, c["fg"] if mono else c["mute"], mono=mono)


def open_panel(s, top):
    c = s.c
    h = 452
    panel(
        s,
        top,
        h,
        "A glTF file opened: converted once, then tables, then tensors",
        "a",
        "python -m prism_cli open scene.glb",
    )
    y = top + 40
    # the file
    ax, aw = 30, 196
    column(s, ax, y, aw, 368, "the file", "glTF 2.0, .glb or .gltf", "g")
    yy = y + 58
    for title, items in (
        (
            "meshes",
            (
                ("triangle primitives:", False),
                ("POSITION, NORMAL,", True),
                ("TEXCOORD_0, COLOR_0", True),
            ),
        ),
        ("materials", (("metallic-roughness,", False), ("textures and images", False))),
        ("lights, cameras", (("KHR_lights_punctual", True),)),
        (
            "nodes",
            (("transforms, instancing:", False), ("EXT_mesh_gpu_instancing", True)),
        ),
        ("refused", (("Draco, meshopt, BasisU", False),)),
    ):
        s.text(ax + 10, yy, title, 11.5, c["fg"], True)
        lines(s, ax + 10, yy + 15, items, 14, 10.5)
        yy += 22 + 14 * len(items)
    # the conversion
    bx, bw = 250, 236
    column(
        s,
        bx,
        y,
        bw,
        368,
        "converted once, on the host",
        "into the data root; found again by its key",
        "y",
    )
    steps = (
        "digest",
        "import",
        "flatten",
        "materials",
        "textures",
        "writing",
        "shared_vertices",
        "uv",
        "entry",
    )
    sy = y + 50
    places = (
        (0, 0, 70),
        (74, 0, 70),
        (148, 0, 70),
        (0, 1, 70),
        (74, 1, 70),
        (148, 1, 70),
        (0, 2, 118),
        (122, 2, 30),
        (156, 2, 62),
    )
    for name, (dx, row, w) in zip(steps, places):
        chip(s, bx + 10 + dx, sy + row * 26, w, 20, name, "y", size=10)
    fy = sy + 92
    s.text(bx + 10, fy, "the scene's files:", 11.5, c["fg"], True)
    for i, (name, what) in enumerate(
        (
            ("NAME.npz", "the mesh"),
            ("NAME_materials.npz", "materials, texels"),
            ("NAME_lighting.npz", "sun, sky, lamps"),
        )
    ):
        s.text(bx + 10, fy + 20 + i * 18, name, 11, c["fg"], mono=True)
        s.text(bx + bw - 10, fy + 20 + i * 18, what, 11, c["mute"], anchor="end")
    s.text(bx + 10, fy + 86, "lights made at once, the sky's", 11, c["mute"])
    s.text(bx + 10, fy + 101, "visibility baked in the background;", 11, c["mute"])
    s.text(bx + 10, fy + 116, "the sun's shadow map left to the card", 11, c["mute"])
    s.text(bx + 10, fy + 146, "convert + digest, seconds:", 11.5, c["fg"], True)
    lines(
        s,
        bx + 10,
        fy + 164,
        (
            ("classroom 4.2", False),
            ("hidden_alley 21.9", False),
            ("lynxsdesign 33.7 (29.8 M triangles)", False),
        ),
        15,
        11,
    )
    s.line(ax + aw + 2, y + 180, bx - 4, y + 180, "a", 1.6)
    # the tables and the tensors
    cx, cw = 510, W - 30 - 510
    column(
        s,
        cx,
        y,
        cw,
        368,
        "the hosts' tables -> tensors",
        "written to the card's DRAM at the load",
        "w",
    )
    rows = (
        (
            "raster",
            "mesh blocks of 32 triangles",
            "(576 words); list pages of",
            "2,048 B, 16 slots",
            "4,788 MB",
            "a",
        ),
        (
            "material.texture",
            "texture pages: 32 x 32 texels,",
            "4,096 B, every mip level",
            "",
            "487 MB",
            "p",
        ),
        (
            "direct.light",
            "LIGHT's table (4,096 B, at most",
            "32 lamps); light pages: shadow",
            "map, sky's planes",
            "69 MB",
            "y",
        ),
        ("post.show", "the display's pages", "", "", "9 MB", "r"),
        (
            "indirect",
            "transport weights in bfp8_b",
            "tiles; the field's pages, twice",
            "with the far field only",
            "",
            "b",
        ),
    )
    ry = y + 48
    for name, a, b, d, mb, colour in rows:
        n = 1 + sum(1 for t in (a, b, d) if t)
        hh = 18 + 14 * (n - 1) + 6
        edge, _, pale = c[colour]
        s.rect(cx + 8, ry, cw - 16, hh, pale, edge, rx=4, sw=1)
        s.text(cx + 16, ry + 15, name, 11.5, c["fg"], True, mono=True)
        if mb:
            s.text(cx + cw - 16, ry + 15, mb, 11.5, edge, True, anchor="end")
        for i, t in enumerate(t for t in (a, b, d) if t):
            s.text(cx + 16, ry + 29 + i * 14, t, 10.5, c["mute"])
        ry += hh + 6
    s.line(bx + bw + 2, y + 180, cx - 4, y + 180, "a", 1.6)
    s.text(
        30,
        top + h - 30,
        "The MB are italian_flat's (3.4 M triangles) with lit, the tensors "
        "of each implementation at its load. Its first picture: 72.0 s cold",
        11,
        c["mute"],
    )
    s.text(
        30,
        top + h - 13,
        "(the file converted, the program built), 23.9 s warm with the "
        "lights baked; less since the hosts' tables are kept (12.3 s).",
        11,
        c["mute"],
    )
    return top + h


def far_panel(s, top):
    c = s.c
    h = 262
    panel(
        s,
        top,
        h,
        "The far field: built on the host afterwards, joined at the next load",
        "b",
    )
    x0, x1 = 170, W - 30
    lanes = (
        ("prism_cli open", top + 50),
        ("the host, beside", top + 112),
        ("the next load", top + 184),
    )
    for name, y in lanes:
        s.text(30, y + 17, name, 12, c["fg"], True)
        s.rule(x0, y + 13, x1, y + 13, 0.5, "2 4")
    o = lanes[0][1]
    chip(s, x0, o, 104, 26, "convert, load", "y", mono=False, size=11.5)
    chip(s, x0 + 110, o, x1 - x0 - 110, 26, "", "g")
    s.text(
        x0 + 120,
        o + 17,
        "gi_threads frames without the indirect light",
        11.5,
        c["fg"],
        True,
    )
    s.text(
        x0 + 110,
        o + 42,
        'the record and the viewer: far_field "absent: no indirect data; '
        'no transport set"',
        11,
        c["mute"],
    )
    b = lanes[1][1]
    s.poly([(x0 + 52, o + 26), (x0 + 52, b + 20), (x0 + 106, b + 20)], "b", 1.2)
    chip(
        s,
        x0 + 110,
        b,
        380,
        42,
        "public_scenes.py indirect NAME --transport sketch",
        "b",
        sub="50,000 elements sampled, a cluster tree, each block traced, compressed",
        size=11.5,
    )
    s.text(x0 + 502, b + 16, "Sponza 78 s (8 threads);", 11, c["mute"])
    s.text(x0 + 502, b + 31, "artists' 8.8 M triangles", 11, c["mute"])
    s.text(x0 + 502, b + 46, "163 s (32 threads)", 11, c["mute"])
    n = lanes[2][1]
    s.poly([(x0 + 300, b + 42), (x0 + 300, n - 2)], "b", 1.2)
    s.text(
        x0 + 306,
        n - 12,
        "NAME_indirect.npz, NAME_transport/",
        11,
        c["b"][0],
        True,
        mono=True,
    )
    chip(s, x0 + 110, n, x1 - x0 - 110, 26, "", "b")
    s.text(
        x0 + 120,
        n + 17,
        'gi_threads with the indirect light: far_field "present"',
        11.5,
        c["fg"],
        True,
    )
    s.text(
        30,
        top + h - 14,
        "The weights (bfp8_b tiles) and the field's model become tensors "
        "of the load that finds the files; the open's frames never wait for them.",
        11,
        c["mute"],
    )
    return top + h


def scene(theme):
    s = Svg(theme, "A glTF file into the renderer's tables and tensors", W)
    y = open_panel(s, 12)
    y = far_panel(s, y + 12)
    return s.finish(y + 12)


if __name__ == "__main__":
    write({"scene": scene}, sys.argv[1] if len(sys.argv) > 1 else None)
