"""The tone step: exposure, saturation and the tone curve of a linear colour."""

import numpy as np

F = np.float32
# The curves by number, the saturation's luminance weights, the filmic fit's numbers.
CURVE_PLAIN, CURVE_FILMIC, CURVE_VIEW = 0, 1, 2
TONE_LUMA = (F(0.2126), F(0.7152), F(0.0722))
FILMIC = (F(2.51), F(0.03), F(2.43), F(0.59), F(0.14))


def tone(colour, exposure, saturation=1.0, curve=CURVE_PLAIN):
    """The tone step of a linear colour (..., 3), float32: x = exposure x colour, then
    saturation s (s = 1: none), then CURVE_PLAIN x / (1 + x), CURVE_FILMIC, or
    CURVE_VIEW none (a view transform tones it)."""
    x = F(exposure) * colour
    s = F(saturation)
    if s != F(1):
        r, g, b = TONE_LUMA
        lum = (x[..., 0:1] * r + x[..., 1:2] * g) + x[..., 2:3] * b
        x = np.maximum(lum + (x - lum) * s, F(0))
    if curve == CURVE_PLAIN:
        return x / (F(1) + x)
    if curve == CURVE_FILMIC:
        a, b, c, d, e = FILMIC
        return np.clip((x * (a * x + b)) / (x * (c * x + d) + e), F(0), F(1))
    if curve == CURVE_VIEW:
        return x
    raise ValueError(
        f"a tone curve is {CURVE_PLAIN} (plain), {CURVE_FILMIC} (filmic) or "
        f"{CURVE_VIEW} (view)"
    )
