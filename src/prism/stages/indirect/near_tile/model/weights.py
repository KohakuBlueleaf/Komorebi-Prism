"""W_T as the card holds it, by region (`regions`): a screen tile's row blocks, a bfp8_b
tile an operand each, MOST_BLOCKS a tile in the screen's tiles' order, and its table;
encoded and decoded. The upsample's weights a screen tile: its quarters of rows in
turn, in each a tap's rows after another, float32."""

import numpy as np
from komorebi import formats

from prism.stages.indirect.near_tile.model.regions import region_records
from prism.stages.indirect.near_tile.steps.step import NS
from prism_common.formats import TILE, format_of
from prism_reference.indirect.near.one_tile import FORM
from prism_reference.scene.frame import frame_grid

WEIGHT_FORMAT = format_of("bfp8_b")
HALF_TILE = FORM["tile"]  # a screen tile's half pixels across and down
SIDE = NS["kNearSide"]  # the plane's half pixels across and down
MOST_BLOCKS = NS["kNearMostBlocks"]  # a tile's W tiles at most
TABLE_WORDS = NS["kNearTableWords"]  # a tile's table
# the region form: the screen tile, its plane, a block's operands at most, the W tiles
# and table words a tile
REGIONS = {
    "tile": HALF_TILE,
    "side": SIDE,
    "most": NS["kNearMostOperands"],
    "most_blocks": MOST_BLOCKS,
    "table_words": TABLE_WORDS,
}


def records(t_op, size):
    """The blended W_T of `t_op` at half rows as the blocks (tiles x MOST_BLOCKS, 32,
    32) float32 and the tables (tiles, TABLE_WORDS) uint32 of a frame of `size`."""
    return region_records(t_op["w"], t_op["owners"], size, REGIONS)


def encode(values):
    """The blocks' bytes (blocks, 1,088) uint8 in bfp8_b."""
    flat = np.asarray(values, np.float32).reshape(-1, TILE, TILE)
    data, _ = formats.to_bytes(flat, WEIGHT_FORMAT.komorebi, "tile")
    return data.reshape(len(flat), WEIGHT_FORMAT.tile_bytes)


def decode(raw):
    """The values (blocks, 32, 32) float32 the card multiplies."""
    raw = np.asarray(raw, np.uint8).reshape(-1, WEIGHT_FORMAT.tile_bytes)
    return formats.from_bytes(
        raw, (len(raw), TILE, TILE), WEIGHT_FORMAT.komorebi, "tile"
    )


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
