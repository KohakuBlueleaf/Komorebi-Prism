"""Camera paths: a view's camera (16,) float32 at WIDTH x HEIGHT, a frame each; a frame's
camera at its size is `prism_reference.scene.camera.sized_camera` of it."""

import numpy as np

F32 = np.float32
STEP = 0.05  # the path forward: the eye's step a frame along the view direction
EYE, AHEAD = slice(0, 3), slice(9, 12)  # the camera's eye and its view direction


def forward(camera, frames):
    """The eye stepping forward: frame i's eye moved i * STEP along the view direction, in
    float32 (the first is the view's own)."""
    camera = np.asarray(camera, dtype=F32)
    out = []
    for index in range(frames):
        moved = camera.copy()
        moved[EYE] = (camera[EYE] + F32(STEP * index) * camera[AHEAD]).astype(F32)
        out.append(moved)
    return out


def still(camera, frames):
    """The view's own camera in every frame."""
    camera = np.asarray(camera, dtype=F32)
    return [camera.copy() for _ in range(frames)]


PATHS = {"forward": forward, "still": still}


def path(name, camera, frames):
    """The cameras of the path `name` (forward, still)."""
    if name not in PATHS:
        raise ValueError(f"path {name!r} is none of {', '.join(PATHS)}")
    return PATHS[name](camera, frames)
