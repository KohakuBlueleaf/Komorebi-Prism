"""The teaser's text: the left column's cards (real lines of the files each names) and
the numbers of the centre and the right, each copied from the source teaser.py names.

A card: (title, colour, mark, source, lines); a line: (text, tint, note, note colour),
tint a colour, None, or "skip" (an elision, drawn muted).
"""

CARDS = [
    (
        "a glTF file, two commands",
        "g",
        "solid",
        "docs/guides/quick_start.md",
        [
            ("python -m prism_cli open <file>.glb \\", "g", "converted once", "mute"),
            ("    --pipeline gi_threads --size 1920 1080 --card 0 \\", "g", "", None),
            ("    --out pictures", None, "a picture from its camera", "mute"),
            ("python -m prism_viewer.server --host 127.0.0.1 \\", "g", "", None),
            ("    --port 8790 --token TOKEN \\", None, "W, A, S, D, the mouse", "mute"),
            (
                "    --pipeline gi_threads --scene <name> --view camera \\",
                "g",
                "",
                None,
            ),
            ("    ...", "skip", "", None),
        ],
    ),
    (
        "the preset",
        "r",
        "solid",
        "configs/pipeline/gi_threads.py",
        [
            ("PIPELINE = Pipeline(", None, "an implementation an item", "mute"),
            ("    ...", "skip", "", None),
            ('        "raster.threads",', "r", "steps of the tile thread", "r"),
            ('        "material.texture.threads",', "r", "", None),
            ('        "direct.shadow_pcf",', None, "", None),
            ('        "indirect.transport.threads",', "a", "the applies: y = M x", "a"),
            ('        "indirect.field_update.threads",', "m", "the job thread", "m"),
            ('        "direct.light.threads_field",', "r", "lit with the field", "r"),
            ('        "post.show.threads",', "p", "the display page", "p"),
            ("    ...", "skip", "", None),
            ('OPTIONS = STAGE_WISE["OPTIONS"] | {', None, "", None),
            ('    "tile_thread": "prism.program.threads.tiles:GI",', "r", "", None),
            ('    "push": False,', "p", "nothing pushed to the host", "p"),
            ('    "update_beside": True,', "m", "the update beside the frames", "m"),
        ],
    ),
    (
        "a stage gives a step",
        "r",
        "solid",
        "stages/direct/light/steps/step.py",
        [
            ("LIGHT = Step(", "r", "", None),
            ("    ...", "skip", "", None),
            ('    requests=("pages",),', None, "light pages asked from DRAM", "mute"),
            ("    reads=(SURFACE_PLANE.name, VISIBILITY.name),", "y", "", None),
            ("    leaves=(VISIBILITY.name,),", "y", "planes kept in L1", "y"),
            ("    ...", "skip", "program/threads/tiles.py:", "mute"),
            ("LIT = TileThread(", "r", "GI is this tile thread", "r"),
            (
                "    steps=(VISIBILITY, LIT_STEP, LIGHT, POST, DEPTH_OUT),",
                "r",
                "",
                None,
            ),
        ],
    ),
    (
        "pulls: a core asks X280 1",
        "w",
        "both",
        "dispatch/c/dispatch_view.c",
        [
            (
                "const int error = kmx_pull_run(command, settings, &event);",
                "w",
                "",
                None,
            ),
            ("...", "skip", "frame/kernels/movement.hpp, mover A:", "mute"),
            ("const uint32_t count = port.next(first, word);", "w", "ask, answer", "w"),
        ],
    ),
    (
        "light transport: y = M x",
        "a",
        "solid",
        "indirect/transport/device.py",
        [
            (
                "    w_in = km.Pair(km.bfp8_b, pages=BLOCK * BLOCKS_A_HALF)",
                "a",
                "",
                None,
            ),
            (
                "    sums: km.L1[km.fp32, OWN, 32, 32] = km.own(push=None)",
                "a",
                "",
                None,
            ),
            ("    ...", "skip", "", None),
            ('        """y = M x on every core of the group."""', None, "", None),
            ("...", "skip", "kernels/apply_compute.hpp:", "mute"),
            (
                "matmul_block(weights, xs, index, place.tile, 0, 1, 1, 1, 1);",
                "a",
                "",
                None,
            ),
        ],
    ),
    (
        "a graph beside the frames",
        "m",
        "solid",
        "indirect/field_update/graph.py",
        [
            ("    applied = graph.command(", "a", "the applies, a bounce a round", "a"),
            ("    ...", "skip", "", None),
            ("    graph.command(", "m", "", None),
            ("        frame,", "m", "", None),
            ("        cluster=1,", "m", "X280 1 takes the new field", "m"),
        ],
    ),
]

# One gi_threads frame on Sponza's overview, 1,920 x 1,080, ms: the dispatcher's
# phases (cores: count, sums, place, tile; X280 1: running, words); the frame; gi less
# its push.
PHASES = [("count", 1.039), ("sums", 0.321), ("place", 1.812), ("tile", 15.429)]
FRAME_MS, GI_LESS_PUSH_MS = 18.610, 22.447
# After one sun move on Sponza, host ms: sun set to the swap frame's end and the frames
# drawn during the update (gi_threads, each apply on every core between two frames);
# gi's stop.
SWAP_MS, FRAMES_DURING, FRAME_DURING_MS, GI_STOP_MS = 172.5, 6, 19.6, 175.1

# Each scene's gi_threads frame over gi's less push, 1,920 x 1,080 (the name shown,
# the ratio).
RATIOS = [
    ("sponza", 0.83),
    ("bistro_interior", 0.73),
    ("breakfast_room", 0.83),
    ("salle_de_bain", 0.88),
    ("modern_hall", 0.78),
    ("modern_living_room", 0.71),
    ("classroom", 0.90),
    ("lynxsdesign 411c", 0.92),
    ("italian_flat", 0.88),
    ("lynxsdesign a018", 1.08),
]

# (file stem, name, triangles, gi_threads ms at 1,920 x 1,080, crop's middle 0..1)
PICTURES = [
    ("sponza", "Sponza", "262 k", 18.610, 0.55),
    ("breakfast_room", "Breakfast Room", "270 k", 15.303, 0.5),
    ("bistro_interior", "Bistro, interior", "1.02 M", 24.182, 0.5),
    ("modern_living_room", "The Modern Living Room", "786 k", 18.196, 0.52),
]

# (what, its condition, Prism, against it, the value's colour)
ROWS = [
    ("pictures", "1,920 frames", "0 pixels differ", "from gi's, byte for byte", "r"),
    ("frame", "29.8 M tris", "102.09 ms", "gi less push 94.16", "p"),
    (
        "sun moved",
        "Sponza",
        f"{FRAMES_DURING} frames drawn",
        f"gi stops {GI_STOP_MS} ms",
        "r",
    ),
    ("lists too small", "Sponza", "grown in 5.3 ms", "reload 6.5 to 7.3 s", "r"),
    ("transport build", "8.8 M tris", "205 s by blocks", "dense + SVD 986 s", "r"),
    ("DRAM written", "lit, Sponza", "8.36 MB a frame", "stage-wise 207.52 MB", "r"),
]

NOTES = [
    (
        "ms: one Blackhole P150A, 1,920 x 1,080, the median frame on the card at each "
        "scene's overview. gi less push: the stage-wise frame less its push"
    ),
    (
        "to the host. Pictures: gi_threads in the viewer at 1,024 x 1,024. Build: on the "
        "host, 8 tracer threads (dense + SVD: 16 CPUs)."
    ),
    (
        "Bytes: the planes written between the stage-wise steps against the display rows. "
        "Lists: a look down 40 degrees, grown against a reload."
    ),
    (
        "Scenes: Crytek Sponza (Frank Meinl, Crytek; CC BY 3.0); Amazon Lumberyard Bistro "
        "(ORCA; CC BY 4.0); Breakfast Room, The Modern Living Room (Wig42; CC BY 3.0)."
    ),
]
