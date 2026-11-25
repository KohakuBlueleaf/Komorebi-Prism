"""The field as the card holds it: 32-bit texels, a has-data bit and three square-root
codes, and their decode."""

import numpy as np

F = np.float32
# A texel a (voxel, direction): bit 31 has data, then red, green, blue codes.
PACK_HAS = 1 << 31
PACK_BITS = (11, 11, 9)
PACK_SHIFTS = (20, 9, 0)


def pack_field(values, has):
    """The field as texels (nv, 6) uint32 and its scale (the largest value, 1 when none
    is above 0): bit 31 where it has data, per channel round(sqrt(v / scale) x max)."""
    v = np.maximum(np.asarray(values, np.float64), 0.0)
    top = float(np.float32(v.max(initial=0.0)))
    scale = np.float32(top if top > 0 else 1.0)
    texels = np.where(has, np.uint32(PACK_HAS), np.uint32(0)).astype(np.uint32)
    for c, (bits, shift) in enumerate(zip(PACK_BITS, PACK_SHIFTS)):
        most = (1 << bits) - 1
        code = np.minimum(np.rint(np.sqrt(v[..., c] / float(scale)) * most), most)
        texels |= np.where(has, code.astype(np.uint32) << np.uint32(shift), 0).astype(
            np.uint32
        )
    return texels, scale


def unpack_field(texels, scale):
    """The values (nv, 6, 3) float32 and has (nv, 6) of pack_field's texels, as the
    card decodes them: c = code x F(1 / (2^bits - 1)), v = (c c) scale."""
    texels = np.asarray(texels, np.uint32)
    has = (texels >> np.uint32(31)) != 0
    out = np.zeros(texels.shape + (3,), F)
    for c, (bits, shift) in enumerate(zip(PACK_BITS, PACK_SHIFTS)):
        most = (1 << bits) - 1
        code = ((texels >> np.uint32(shift)) & np.uint32(most)).astype(F)
        unit = code * F(1.0 / most)
        out[..., c] = np.where(has, (unit * unit) * F(scale), F(0))
    return out, has
