"""The card's numbers emulated: bfloat16 rounding, the bfp8_b encode and the apply in
them."""

import numpy as np

from prism_reference.indirect.hmatrix.apply import apply

F = np.float32


def round_bits(a, bits):
    """a rounded to `bits` significant bits, half to even (bfloat16: 8)."""
    m, e = np.frexp(np.asarray(a, np.float64))
    return np.ldexp(np.rint(np.ldexp(m, bits)), e - bits).astype(F)


def bfp8_b(a):
    """a (size a multiple of 16) in bfp8_b by the host encode: each 16 consecutive
    numbers share their largest exponent, magnitudes rounded half to even to 7 bits."""
    g = np.asarray(a, F).reshape(-1, 16).astype(np.float64)
    top = np.abs(g).max(1, keepdims=True)
    _, e = np.frexp(np.where(top > 0, top, 1.0))
    unit = np.ldexp(1.0, e.astype(np.int64) - 1 - 6)
    q = np.minimum(np.rint(np.abs(g) / unit), 127)
    return np.where(top > 0, np.sign(g) * q * unit, 0.0).astype(F).reshape(np.shape(a))


def card_apply(blocks, weights, x, chunk=1 << 24):
    """The apply with every weight bfp8_b, x's and t's rows bfloat16, sums float32."""
    quantised = np.empty_like(weights)
    for s in range(0, len(weights), chunk):
        quantised[s : s + chunk] = bfp8_b(weights[s : s + chunk])
    return apply(blocks, quantised, x, lambda v: round_bits(v, 8))
