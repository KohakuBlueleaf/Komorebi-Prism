"""SHOW's thresholds table and the writer's conversion on the host, against the
reference's display rule (prism_reference.post.display.to_srgb8, or another transfer);
the largest power transfer's gamma whose table the writer's buckets hold."""

import math
from functools import partial
from pathlib import Path

import numpy as np

from prism.core.headers import constexpr
from prism_reference.post.display import to_power8, to_srgb8

KERNELS = Path(__file__).resolve().parent.parent / "kernels"
SHOW = constexpr(KERNELS / "show.h")
TABLE_SEED = 7  # table_check's random colours
TABLE_UNIFORM = 1 << 20  # its colours in [0, 1)
TABLE_WIDE = 1 << 16  # its colours in [-0.5, 1.5)
TABLE_LOW = 1 << 16  # its colours from the bucket base to 1.0, even in the logarithm
FIRST_LEVEL = 0.5 / 255  # the transferred value that rounds to byte 1
GAMMA_PLACES = 2  # most_gamma rounded down to this many decimals


def show_table(transfer=to_srgb8):
    """SHOW's table: word k (1 to 255) the bits of the smallest float32 whose 8-bit
    value by `transfer` is k (monotonic in a float32's bits on [0, 1]); word 0 the bits
    of -0, never read."""
    wanted = np.arange(1, 256)
    low = np.zeros(255, dtype=np.int64)
    high = np.full(255, np.float32(1.0).view(np.uint32), dtype=np.int64)
    while (low < high).any():
        middle = (low + high) // 2
        value = transfer(middle.astype(np.uint32).view(np.float32))
        reached = value >= wanted
        high = np.where(reached, middle, high)
        low = np.where(reached, low, middle + 1)
    table = np.zeros(SHOW["kShowTableWords"], dtype=np.uint32)
    table[0] = 0x80000000
    table[1:] = low
    if not SHOW["kShowBucketBase"] < low[0] <= low[-1] < SHOW["kShowOne"]:
        raise ValueError("the thresholds leave the writer's buckets")
    return table


def most_gamma():
    """The largest power transfer's gamma (rounded down to GAMMA_PLACES) whose first
    threshold, FIRST_LEVEL ** gamma, stays over the writer's bucket base."""
    base = float(np.uint32(SHOW["kShowBucketBase"]).view(np.float32))
    scale = 10**GAMMA_PLACES
    return math.floor(math.log(base) / math.log(FIRST_LEVEL) * scale) / scale


def show_buckets(table, buckets=None):
    """The writer's buckets for `table` (convert.hpp thresholds_of): each bucket's
    first value from the first threshold's bucket; those under it kept from
    `buckets` (zeros if None)."""
    base, one = SHOW["kShowBucketBase"], SHOW["kShowOne"]
    shift = SHOW["kShowBucketShift"]
    if buckets is None:
        buckets = np.zeros((one - base) >> shift, dtype=np.int64)
    thresholds = table.view(np.int32)
    first = (int(thresholds[1]) - base) >> shift
    starts = base + (np.arange(first, len(buckets), dtype=np.int64) << shift)
    buckets[first:] = np.searchsorted(thresholds[1:], starts, side="right")
    return buckets


def show_bytes(table, colour, buckets=None):
    """The writer's conversion step for step (convert.hpp show_byte): each float32's
    bits as a signed word; under the first threshold 0, from 1.0 255, else the
    bucket's value (show_buckets over `buckets`) stepped over the thresholds."""
    signed = np.ascontiguousarray(colour, dtype=np.float32).view(np.int32).ravel()
    thresholds = table.view(np.int32)
    base, one = SHOW["kShowBucketBase"], SHOW["kShowOne"]
    shift, last = SHOW["kShowBucketShift"], len(table) - 1
    buckets = show_buckets(table, buckets)
    first = thresholds[1]
    out = np.where(signed < first, 0, last).astype(np.int64)
    inside = np.flatnonzero((signed >= first) & (signed < one))
    index = buckets[(signed[inside].astype(np.int64) - base) >> shift]
    while True:
        step = (index < last) & (
            signed[inside] >= thresholds[np.minimum(index + 1, last)]
        )
        if not step.any():
            break
        index = index + step
    out[inside] = index
    return out.astype(np.uint8).reshape(np.shape(colour))


def table_values(table):
    """The colours table_check converts: both sides of every threshold, the clamp's
    ends and random colours."""
    bits = table[1:].astype(np.int64)
    edges = np.concatenate([bits, bits - 1, bits + 1]).astype(np.uint32)
    special = np.array(
        [0.0, -0.0, -1.0, 1.0, 1.5, 1e30, -1e30, 1e-30, 0.05, 0.08], dtype=np.float32
    )
    rng = np.random.default_rng(TABLE_SEED)
    return np.concatenate(
        [
            edges.view(np.float32),
            special,
            rng.random(TABLE_UNIFORM, dtype=np.float32),
            rng.uniform(-0.5, 1.5, TABLE_WIDE).astype(np.float32),
        ]
    )


def table_check(table):
    """The table's bytes against to_srgb8 on table_values, with fresh buckets and with
    the buckets the widest power transfer's table left: the number that differ."""
    values = np.concatenate([table_values(table), low_values()])
    want = to_srgb8(values)
    widest = show_table(partial(to_power8, gamma=most_gamma()))
    kept = show_buckets(widest)
    return int((show_bytes(table, values) != want).sum()) + int(
        (show_bytes(table, values, kept) != want).sum()
    )


def low_values():
    """Random colours from the writer's bucket base to 1.0, even in the logarithm:
    those between the widest table's first threshold and another's among them."""
    rng = np.random.default_rng(TABLE_SEED)
    base = float(np.uint32(SHOW["kShowBucketBase"]).view(np.float32))
    return np.exp(rng.uniform(math.log(base), 0.0, TABLE_LOW)).astype(np.float32)


def displayed(colour):
    """A colour (H, W, 3) float32 as the display's pixels (H, W, 4) uint8: to_srgb8,
    alpha 255."""
    out = np.full(np.shape(colour)[:2] + (4,), 255, dtype=np.uint8)
    out[..., :3] = to_srgb8(colour)
    return out
