"""The camera array (16,) float32: making one, and sizing a view's to a frame."""

import numpy as np

from prism_reference.scene.frame import WIDTH, frame_grid


def normalize(v):
    """Unit vector of a float64 3-vector (sqrt and division only)."""
    return v / np.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def cross(a, b):
    """Cross product of two float64 3-vectors."""
    return np.array(
        [
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        ]
    )


def sized_camera(camera, size):
    """The camera (16,) float32 of a view at frame size (W, H) from its camera at
    WIDTH x HEIGHT: principal point (W / 2, H / 2), focal length times max(W, H) / WIDTH.
    """
    width, height = (int(n) for n in size)
    frame_grid((width, height))
    out = np.array(camera, dtype=np.float32)
    out[12] = np.float32(np.float64(out[12]) * max(width, height) / WIDTH)
    out[13], out[14] = np.float32(width / 2), np.float32(height / 2)
    return out


def with_size(view, size):
    """The view (a scene dict with its WIDTH x HEIGHT camera) at frame size (W, H): its
    `size` entry and `sized_camera`."""
    width, height = (int(n) for n in size)
    camera = sized_camera(view["camera"], (width, height))
    return {**view, "size": (width, height), "camera": camera}
