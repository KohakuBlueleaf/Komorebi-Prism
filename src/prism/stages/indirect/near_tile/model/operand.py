"""S_T and E as the card holds them: the operand of a screen tile (its WIDTH colours in
bfloat16) from a frame's linear radiance and the field's packed values, and the
product's E at half rows (float32) of the records' bfp8_b values."""

import numpy as np
from komorebi import formats

from prism.stages.indirect.near_tile.model.weights import HALF_TILE
from prism_reference.indirect.near.half import half_of
from prism_reference.indirect.near.one_tile import tile_operand
from prism_reference.scene.frame import frame_grid

LIGHT_WORDS = 3 * HALF_TILE * HALF_TILE  # E of a tile: a channel's half pixels each
PAGE_WORDS = 1024  # a tile's page of E: LIGHT_WORDS, then 0


def bf16(values):
    """`values` as bfloat16 holds them (Komorebi's encode), float32."""
    array = np.asarray(values, np.float32)
    raw, _ = formats.to_bytes(array.reshape(-1, 1), "bfloat16", "row")
    return formats.from_bytes(raw, (array.size, 1), "bfloat16", "row").reshape(
        array.shape
    )


def operands(t_op, radiance, values, ambient, size):
    """S_T (tiles, WIDTH, 3) in bfloat16 of a frame of `size`, the screen's tiles row by
    row: the cells' means of `radiance` (H, W, 3 full pixels), the far groups of the
    field's `values` (entries, 3), the `ambient`."""
    half = half_of(np.asarray(radiance, np.float64))
    s = tile_operand(t_op, half, np.zeros_like(half), values, ambient)
    across, down = frame_grid(size)
    out = np.zeros((down, across) + s.shape[2:], np.float32)
    out[: s.shape[0], : s.shape[1]] = s
    return bf16(out.reshape(down * across, *s.shape[2:]))


def light_pages(weights, s):
    """E (tiles, PAGE_WORDS) float32 of the records' values (tiles, 8, 32, 32) times
    S_T (tiles, WIDTH, 3): a channel's 256 half pixels (row by row) after another."""
    rows = np.asarray(weights, np.float32).reshape(len(s), HALF_TILE * HALF_TILE, -1)
    e = np.einsum("tpk,tkc->tcp", rows, np.asarray(s, np.float32), dtype=np.float32)
    out = np.zeros((len(s), PAGE_WORDS), np.float32)
    out[:, :LIGHT_WORDS] = e.reshape(len(s), LIGHT_WORDS)
    return out
