"""The card's numbers emulated: bfloat16 rounding, the bfp8_b encode and the apply in
them."""

import numpy as np

from prism_reference.indirect.hmatrix.apply import apply

F = np.float32
SHIFT = 24 - 7  # a bfp8_b magnitude: 7 of the 24 bits
SHIFTED, TIE = (1 << SHIFT) - 1, 1 << (SHIFT - 1)


def round_bits(a, bits):
    """a rounded to `bits` significant bits, half to even (bfloat16: 8)."""
    m, e = np.frexp(np.asarray(a, np.float64))
    return np.ldexp(np.rint(np.ldexp(m, bits)), e - bits).astype(F)


def bfp8_b(a):
    """a (size a multiple of 16) in bfp8_b by the host encode: each 16 consecutive
    numbers share their largest exponent; a magnitude's 24 bits shifted to it (the bits
    shifted out dropped), then rounded to 7 bits, ties to even; subnormals 0."""
    w = np.ascontiguousarray(a, F).reshape(-1, 16).view(np.uint32).astype(np.int64)
    exp, man = (w >> 23) & 0xFF, w & 0x7FFFFF
    zero = exp == 0
    shared = np.where(zero, 0, exp).max(1, keepdims=True)
    man = ((1 << 23) | man) >> np.minimum(shared - exp, 31)
    rest, man = man & SHIFTED, man >> SHIFT
    man = man + ((rest > TIE) | ((rest == TIE) & ((man & 1) == 1)))
    man = np.where(zero, 0, np.minimum(man, 127))
    value = np.ldexp(man.astype(np.float64), shared - 127 - 6)
    value = np.where((w >> 31) == 1, -value, value)
    return value.astype(F).reshape(np.shape(a))


def card_apply(blocks, weights, x, chunk=1 << 24):
    """The apply with every weight bfp8_b, x's and t's rows bfloat16, sums float32."""
    quantised = np.empty_like(weights)
    for s in range(0, len(weights), chunk):
        quantised[s : s + chunk] = bfp8_b(weights[s : s + chunk])
    return apply(blocks, quantised, x, lambda v: round_bits(v, 8))
