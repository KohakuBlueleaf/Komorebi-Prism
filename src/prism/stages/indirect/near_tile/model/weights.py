"""W_T as the card holds it: a screen tile's record of RECORD_TILES bfp8_b tiles, tile k
the half rows 2k and 2k + 1 (a half pixel a row, its WIDTH columns), one record after
another in the screen's tiles' order; encoded and decoded. The upsample's weights a
screen tile: its quarters of rows in turn, in each a tap's rows after another, float32.
"""

import numpy as np
from komorebi import formats

from prism_common.formats import TILE, format_of
from prism_reference.indirect.near.one_tile import FORM
from prism_reference.indirect.near.tile_far import WIDTH
from prism_reference.scene.frame import frame_grid

WEIGHT_FORMAT = format_of("bfp8_b")
HALF_TILE = FORM["tile"]  # a screen tile's half pixels across and down
RECORD_TILES = HALF_TILE * HALF_TILE // TILE  # a record's tiles
RECORD_BYTES = RECORD_TILES * WEIGHT_FORMAT.tile_bytes


def records(w, size):
    """W_T (h, w, WIDTH) at half rows as the records (tiles, RECORD_TILES, 32, 32)
    float32 of a frame of `size`: the screen tiles row by row, 0 past the frame."""
    across, down = frame_grid(size)
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


def upsample_records(weights, size, quarters):
    """The upsample's weights (H, W, taps) as pages (tiles x quarters, taps x 1,024 /
    quarters) float32 of a frame of `size`: a tile's quarters of rows in turn, in a
    quarter each tap's rows after another; the screen's tiles row by row, 0 past it."""
    across, down = frame_grid(size)
    taps = weights.shape[-1]
    full = np.zeros((down * TILE, across * TILE, taps), np.float32)
    full[: weights.shape[0], : weights.shape[1]] = weights
    rows = TILE // quarters
    blocks = full.reshape(down, quarters, rows, across, TILE, taps)
    blocks = blocks.transpose(0, 3, 1, 5, 2, 4)
    return blocks.reshape(down * across * quarters, taps * rows * TILE)
