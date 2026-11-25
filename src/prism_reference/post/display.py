"""The conversion for display: a colour in [0, 1] to 8-bit sRGB-like bytes; the power
transfer of a given gamma and the standard piecewise sRGB transfer beside it."""

import numpy as np

GAMMA = 2.2  # to_srgb8's
SRGB_KNEE = 0.0031308  # the standard sRGB transfer: linear under the knee, a power over
SRGB_SLOPE = 12.92
SRGB_GAMMA = 2.4
SRGB_SCALE, SRGB_OFFSET = 1.055, 0.055


def to_srgb8(linear):
    """Float RGB in [0, 1] (clamped) to display bytes with a 1/2.2 gamma."""
    x = np.clip(np.asarray(linear, dtype=np.float64), 0.0, 1.0) ** (1 / 2.2)
    return np.rint(x * 255).astype(np.uint8)


def to_power8(linear, gamma=GAMMA):
    """Float RGB in [0, 1] (clamped) to display bytes with a 1/gamma power."""
    x = np.clip(np.asarray(linear, dtype=np.float64), 0.0, 1.0) ** (1 / gamma)
    return np.rint(x * 255).astype(np.uint8)


def to_srgb_standard8(linear):
    """Float RGB in [0, 1] (clamped) to display bytes by the standard piecewise sRGB
    transfer."""
    x = np.clip(np.asarray(linear, dtype=np.float64), 0.0, 1.0)
    curve = SRGB_SCALE * x ** (1 / SRGB_GAMMA) - SRGB_OFFSET
    return np.rint(np.where(x <= SRGB_KNEE, SRGB_SLOPE * x, curve) * 255).astype(
        np.uint8
    )
