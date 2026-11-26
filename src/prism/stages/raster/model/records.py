"""The card's records: the 32-word triangle record and the mesh as blocks of 32 triangles."""

import numpy as np

from prism.stages.raster.model.numbers import (
    BLOCK_SLOTS,
    BLOCK_WORDS,
    LANES,
    NEG_ZERO_NEIGHBOUR,
    SLOT,
    K,
)


def bits(x):
    """float32 values as uint32 bit patterns."""
    return np.ascontiguousarray(x, dtype=np.float32).view(np.uint32)


def half_bits(x):
    """Integers below 2048 as float16 bit patterns (exact), in uint32."""
    x = np.asarray(x)
    if x.min(initial=0) < 0 or x.max(initial=0) >= 2048:
        raise ValueError("a box column is not exact in float16")
    return x.astype(np.float16).view(np.uint16).astype(np.uint32)


def pack_records(records, wide=False):
    """The 32-word card record of every triangle record of `setup.setup`; `wide` the
    box columns as a wide build holds them (float32, grid.h), else float16."""
    count = len(records["tri"])
    packed = np.zeros((count, SLOT), dtype=np.uint32)
    packed[:, K["kRecA"] : K["kRecA"] + 3] = bits(records["a"])
    packed[:, K["kRecB"] : K["kRecB"] + 3] = bits(records["b"])
    packed[:, K["kRecC"] : K["kRecC"] + 3] = bits(records["c"])
    packed[:, K["kRecT"] : K["kRecT"] + 3] = np.where(
        records["top_left"], NEG_ZERO_NEIGHBOUR, 0
    )
    packed[:, K["kRecW"] : K["kRecW"] + 3] = bits(records["w_planes"])
    colour_planes = records["c_planes"]  # (n, coefficient, channel)
    for channel in range(3):
        column = K["kRecCol"] + 3 * channel
        packed[:, column : column + 3] = bits(colour_planes[:, :, channel])
    box = records["box"].astype(np.int64)
    columns = bits if wide else half_bits
    packed[:, K["kRecX0"]] = columns(box[:, 0])
    packed[:, K["kRecX1"]] = columns(box[:, 1] + 1)
    packed[:, K["kRecY0"]] = box[:, 2].astype(np.uint32)
    packed[:, K["kRecY1"]] = box[:, 3].astype(np.uint32)
    packed[:, K["kRecTri"]] = bits(records["tri"].astype(np.float32))
    packed[:, K["kRecIndex"]] = np.arange(count, dtype=np.uint32)
    return packed


def window_words(slots):
    """Window word of (slot, lane) for `slots` slots of 32 lanes: (slots, 32)."""
    slot = np.arange(slots)[:, None]
    lane = np.arange(LANES)[None, :]
    return 64 * (slot // 2) + slot % 2 + 2 * lane


def mesh_blocks(scene):
    """(blocks, 576) uint32: every triangle's corners and colours, 32 triangles a block,
    in the destination register's window order; the last block padded with zero
    corners."""
    indices = scene["indices"]
    triangles = len(indices)
    blocks = -(-triangles // LANES)
    positions = np.zeros((blocks * LANES, 3, 3), dtype=np.float32)
    colours = np.zeros((blocks * LANES, 3, 3), dtype=np.float32)
    positions[:triangles] = scene["positions"][indices]
    colours[:triangles] = scene["colors"][indices]
    # vectors (block, slot, lane): slot 3 k + i is coordinate i of corner k
    vectors = np.concatenate(
        [positions.reshape(blocks, LANES, 9), colours.reshape(blocks, LANES, 9)], axis=2
    ).transpose(0, 2, 1)
    block_words = np.zeros((blocks, BLOCK_WORDS), dtype=np.uint32)
    block_words[:, window_words(BLOCK_SLOTS)] = vectors.view(np.uint32)
    return block_words
