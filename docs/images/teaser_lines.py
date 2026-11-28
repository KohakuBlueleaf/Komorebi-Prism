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
            ("...", "skip", "field_update/graph.py, the job thread:", "mute"),
            ("    applied = graph.command(", "a", "the applies, a bounce a round", "a"),
            ("    ...", "skip", "", None),
            ("    graph.command(", "m", "", None),
            ("        frame,", "m", "", None),
            ("        cluster=1,", "m", "X280 1 takes the new field", "m"),
        ],
    ),
]

# One gi_threads frame on Sponza's overview, 1,920 x 1,080, ms: the dispatcher's
# phases while the camera moves (cores: count, sums, place, tile); the frame moving and
# standing (the lists kept: the tile alone); gi less its push.
PHASES = [("count", 1.079), ("sums", 0.324), ("place", 1.879), ("tile", 16.720)]
MOVES_MS, STANDS_MS, GI_LESS_PUSH_MS = 20.003, 16.795, 24.125
# After one sun move on Sponza (its 3 bounces), host ms: sun set to the swap frame's end
# and the frames drawn during the update (gi_threads, each apply on every core between
# two frames); gi's stop.
BOUNCES, SWAP_MS, FRAMES_DURING, GI_STOP_MS = 3, 161.4, 5, 173.4

# Each scene's gi_threads frame over gi's less push, 1,920 x 1,080 (the name shown,
# standing, moving).
RATIOS = [
    ("sponza", 0.70, 0.83),
    ("bistro_interior", 0.59, 0.71),
    ("breakfast_room", 0.72, 0.84),
    ("salle_de_bain", 0.69, 0.84),
    ("modern_hall", 0.74, 0.78),
    ("modern_living_room", 0.56, 0.75),
    ("classroom_3f41", 0.65, 0.78),
    ("lynxsdesign_b495", 0.51, 0.75),
    ("italian_flat_6965", 0.57, 0.78),
    ("lynxsdesign_6efc", 0.38, 0.67),
]

# (file stem, name, triangles, gi_threads ms standing at 1,920 x 1,080, crop's middle
# 0..1)
PICTURES = [
    ("sponza", "Sponza", "262 k", 16.795, 0.55),
    ("bistro_interior", "Bistro, interior", "1.02 M", 21.154, 0.5),
    ("breakfast_room", "Breakfast Room", "270 k", 14.056, 0.55),
    ("italian_flat", "Italian Flat", "4.8 M", 29.680, 0.5),
]

# (what, its condition, Prism, against it (one line or several), the value's colour)
ROWS = [
    ("pictures", "3,840 frames", "0 pixels differ", ("from gi's, byte for byte",), "r"),
    (
        "frame",
        "29.8 M tris",
        "37.75 ms standing",
        ("moving 67.16", "gi less push 100.58"),
        "r",
    ),
    (
        "3,840 x 2,160",
        "Sponza",
        "57.08 ms standing",
        ("moving 66.51", "gi: past L1"),
        "r",
    ),
    (
        "sun moved",
        "Sponza",
        f"{FRAMES_DURING} frames drawn",
        (f"gi stops {GI_STOP_MS} ms", f"the scene's {BOUNCES} bounces"),
        "r",
    ),
    (
        "Italian Flat",
        "the same glTF",
        "29.68 ms a frame",
        ("Cycles(glTF): 43.4 s,", "256 samples,", "one V100-class GPU"),
        "r",
    ),
]

NOTES = [
    (
        "ms: one Blackhole P150A, 1,920 x 1,080, the median frame on the card at each "
        "scene's view. Standing: the camera still, the lists kept, the tile pull alone;"
    ),
    (
        "moving: the lists made again each frame. gi less push: the stage-wise frame less "
        "its push to the host. Pictures: gi_threads in the viewer at 1,920 x 1,080;"
    ),
    (
        "Italian Flat's at 1,280 x 720 at the camera of the comparison with Cycles, which "
        "reads the same glTF file (docs/performance/gltf_truth.md)."
    ),
    (
        "Curved surfaces are drawn with flat triangles (a glTF file's vertex normals are "
        "not carried yet), visible on Sponza's banners."
    ),
    (
        "Scenes: Crytek Sponza (Frank Meinl, Crytek; CC BY 3.0); Amazon Lumberyard Bistro "
        "(ORCA; CC BY 4.0); Breakfast Room (Wig42; CC BY 3.0);"
    ),
    "Italian Flat (Flavio Della Tommasa, malapixel.com; CC BY).",
]
