"""S_T and E as the card holds them: the operand of a screen tile (its WIDTH colours in
bfloat16) from a frame's linear radiance and the field's packed values, and the
product's E on the tiles' planes (float32) of the blocks' bfp8_b values and tables."""

import numpy as np
from komorebi import formats

from prism_reference.indirect.near.half import half_of
from prism_reference.indirect.near.one_tile import tile_operand
from prism_reference.scene.frame import frame_grid


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


def operand_raw(tiles):
    """The operands' tiles (tiles, 32, 32) as their bfloat16 pages (tiles, 2,048) uint8."""
    data, _ = formats.to_bytes(np.asarray(tiles, np.float32), "bfloat16", "tile")
    return data.reshape(len(tiles), -1)


def region_light(blocks, tables, s, side):
    """E (tiles, 3, side, side) float32 of the region blocks' values (tiles x most,
    32, 32) and tables (tiles, words) times the operands S_T (tiles, WIDTH, 3): each
    block's rows added at their places."""
    s = np.asarray(s, np.float32)
    out = np.zeros((len(tables), 3, side * side), np.float32)
    for t, page in enumerate(tables):
        for i in range(int(page[0])):
            entry = page[1 + 20 * i : 21 + 20 * i]
            count, first = int(entry[0]), int(entry[1])
            index = [
                entry[2] & 0xFFFF,
                entry[2] >> 16,
                entry[3] & 0xFFFF,
                entry[3] >> 16,
            ]
            e = np.zeros((32, 3), np.float32)
            for k in range(count):
                e += blocks[first + k][:, : s.shape[1]] @ s[index[k]]
            places = np.stack([entry[4:] & 0xFFFF, entry[4:] >> 16], 1).reshape(-1)
            keep = places != 0xFFFF
            np.add.at(out[t], (slice(None), places[keep]), e[keep].T)
    return out.reshape(len(tables), 3, side, side)
