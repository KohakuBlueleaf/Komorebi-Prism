"""W_T as the card holds it: a screen tile's record of RECORD_TILES bfp8_b tiles, tile k
the half rows 2k and 2k + 1 (a half pixel a row, its WIDTH columns), one record after
another in the screen's tiles' order; encoded and decoded."""

import numpy as np
from komorebi import formats

from prism_common.formats import TILE, format_of
from prism_reference.indirect.near.one_tile import FORM
from prism_reference.indirect.near.tile_far import WIDTH

WEIGHT_FORMAT = format_of("bfp8_b")
HALF_TILE = FORM["tile"]  # a screen tile's half pixels across and down
RECORD_TILES = HALF_TILE * HALF_TILE // TILE  # a record's tiles
RECORD_BYTES = RECORD_TILES * WEIGHT_FORMAT.tile_bytes


def tile_grid(size):
    """The screen tiles (across, down) of a frame of `size` (width, height)."""
    return -(-int(size[0]) // (2 * HALF_TILE)), -(-int(size[1]) // (2 * HALF_TILE))


def records(w, size):
    """W_T (h, w, WIDTH) at half rows as the records (tiles, RECORD_TILES, 32, 32)
    float32 of a frame of `size`: the screen tiles row by row, 0 past the frame."""
    across, down = tile_grid(size)
    full = np.zeros((down * HALF_TILE, across * HALF_TILE, WIDTH), np.float32)
    full[: w.shape[0], : w.shape[1]] = w
    blocks = full.reshape(down, HALF_TILE, across, HALF_TILE, WIDTH).swapaxes(1, 2)
    return blocks.reshape(down * across, RECORD_TILES, TILE, WIDTH)


def encode(values):
    """The records' bytes (tiles, RECORD_BYTES) uint8 in bfp8_b."""
    flat = np.asarray(values, np.float32).reshape(-1, TILE, TILE)
    data, _ = formats.to_bytes(flat, WEIGHT_FORMAT.komorebi, "tile")
    return data.reshape(len(values), RECORD_BYTES)


def decode(raw):
    """The values (tiles, RECORD_TILES, 32, 32) float32 the card multiplies."""
    raw = np.asarray(raw, np.uint8).reshape(-1, WEIGHT_FORMAT.tile_bytes)
    values = formats.from_bytes(
        raw, (len(raw), TILE, TILE), WEIGHT_FORMAT.komorebi, "tile"
    )
    return values.reshape(-1, RECORD_TILES, TILE, TILE)
