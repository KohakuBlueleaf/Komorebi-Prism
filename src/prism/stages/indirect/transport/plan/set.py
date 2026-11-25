"""A transport set's files: the blocks in tiles, the weights and the vectors."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from prism_common.formats import TILE


@dataclass
class Set:
    """One set's files: the blocks (in tiles), the weights and the vectors."""

    folder: Path
    row0: np.ndarray  # receiver tiles row0 : row1 of each block
    row1: np.ndarray
    col0: np.ndarray  # source tiles col0 : col1
    col1: np.ndarray
    rank: np.ndarray  # rank tiles R (0 for a dense block)
    offset_a: np.ndarray  # numbers into weights.f32
    offset_b: np.ndarray
    tiles: int  # receiver (and source) tiles of the matrix

    @property
    def blocks(self):
        return len(self.row0)

    def weights(self):
        """weights.f32 as float32 numbers, mapped."""
        return np.memmap(self.folder / "weights.f32", np.float32, "r")

    def vector(self, name):
        """x.npy, y_float.npy, ...: [N, 3] float32."""
        return np.load(self.folder / name)


def load(folder):
    """The set in `folder` (blocks.npz and the rest, as its README.md lays them out)."""
    folder = Path(folder)
    b = np.load(folder / "blocks.npz")
    if not np.all(b["scale"] == 1.0):
        raise ValueError(f"{folder}: a block's scale is not 1 (not applied here)")
    tiles = len(np.load(folder / "perm.npy")) // TILE
    return Set(
        folder,
        b["row0"] // TILE,
        b["row1"] // TILE,
        b["col0"] // TILE,
        b["col1"] // TILE,
        b["rank_padded"] // TILE * (b["kind"] == 1),
        b["offset_a"],
        b["offset_b"],
        tiles,
    )
