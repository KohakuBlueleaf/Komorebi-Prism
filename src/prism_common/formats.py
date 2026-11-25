"""The card's number formats by name: a tile's bytes, the host's numpy type, Komorebi's
name of the format."""

from dataclasses import dataclass

import numpy as np

TILE = 32


@dataclass(frozen=True)
class Format:
    """One format of the card's tiles."""

    name: str
    tile_bytes: int
    dtype: np.dtype
    komorebi: str


FORMATS = {
    item.name: item
    for item in (
        Format("bfp8_b", 1088, np.dtype(np.float32), "bfp8_b"),
        Format("bf16", 2048, np.dtype(np.float32), "bfloat16"),
        Format("fp32", 4096, np.dtype(np.float32), "float32"),
        Format("u32", 4096, np.dtype(np.uint32), "uint32"),
    )
}


def format_of(name):
    """The format named `name`."""
    if name not in FORMATS:
        raise KeyError(f"no format {name!r}; the card's: {', '.join(FORMATS)}")
    return FORMATS[name]
