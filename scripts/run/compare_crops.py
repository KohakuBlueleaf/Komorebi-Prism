"""Named crops of the scenes `compare.py` compares, by the scene's stem (the glTF file's,
its folder's when the file is called `scene`) and the camera (None: the render camera):
{name: (x0, y0, x1, y1)} as fractions of the picture, x right, y down."""

CROPS = {
    ("italian_flat", None): {
        "shadow_edge": (0.914, 0.18, 1.0, 0.417),
        "light_patch": (0.61, 0.61, 0.734, 0.708),
        "fabric": (0.336, 0.68, 0.61, 0.93),
        "cushion": (0.336, 0.444, 0.477, 0.583),
        "wall": (0.227, 0.042, 0.32, 0.32),
        "glass": (0.594, 0.09, 0.84, 0.361),
        "books": (0.055, 0.36, 0.195, 0.5),
    },
    ("lynxsdesign", None): {
        "shadow_edge": (0.45, 0.65, 0.61, 0.82),
        "stairs": (0.42, 0.14, 0.633, 0.667),
        "fabric": (0.64, 0.78, 0.985, 1.0),
        "wall_cove": (0.578, 0.19, 0.825, 0.31),
        "ceiling": (0.64, 0.03, 0.845, 0.19),
        "glass": (0.395, 0.055, 0.574, 0.36),
        "painting": (0.016, 0.014, 0.172, 0.57),
        "slats": (0.195, 0.0, 0.313, 0.57),
    },
}


def crops_of(stem, camera):
    """The named crops of a scene's view; empty when it has none."""
    return dict(CROPS.get((stem, camera), {}))
