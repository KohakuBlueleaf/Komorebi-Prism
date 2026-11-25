"""Float32 vector arithmetic over the last axis, in a fixed order."""

import numpy as np

F = np.float32


def dot3(a, b):
    """(a0 b0 + a1 b1) + a2 b2 over the last axis (float32, in this order)."""
    return (a[..., 0] * b[..., 0] + a[..., 1] * b[..., 1]) + a[..., 2] * b[..., 2]


def normalized(v):
    """v / |v| over the last axis; zero where |v| is zero."""
    length = np.sqrt(dot3(v, v))
    safe = np.where(length > 0, length, F(1))
    return np.where((length > 0)[..., None], v / safe[..., None], F(0))


def cross3(a, b):
    """The cross product over the last axis (float32)."""
    return np.stack(
        [
            a[..., 1] * b[..., 2] - a[..., 2] * b[..., 1],
            a[..., 2] * b[..., 0] - a[..., 0] * b[..., 2],
            a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0],
        ],
        axis=-1,
    )
