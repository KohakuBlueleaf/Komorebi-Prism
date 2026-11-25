"""The display's pages: a tile a page of 32 x 32 pixels, the image they untile into, the
pages a frame pushes, and COPY's pages of a plane."""

from typing import NamedTuple

import numpy as np

from prism.stages.raster.model.frame import TILE_ORDER
from prism.stages.raster.model.numbers import GRID, K

TILE = 32  # a tile's pixels a side
PIXEL_BYTES = 4  # R, G, B, 255
ROW_TILES = GRID["kGridDefault"]  # COPY's tiles a row of its pages


class FramePages(NamedTuple):
    """The display tensor's first `pages` (the frame's tiles), as a transfer takes a
    tensor: a frame pushes and reads its own pages, not the capacity's."""

    address: int
    page_bytes: int
    aligned_page_bytes: int
    pages: int
    in_dram: bool = True

    @classmethod
    def of(cls, tensor, pages):
        return cls(tensor.address, tensor.page_bytes, tensor.aligned_page_bytes, pages)


def untile(pages, image, grid):
    """The display's pages (tile ty TX + tx of `grid` (TX, TY); 32 rows of 32 pixels
    of 4 bytes) into `image` (32 TY, 32 TX, 4), the padded frame."""
    across, down = grid
    image.reshape(down, TILE, across, TILE, PIXEL_BYTES)[...] = (
        np.asarray(pages)[: across * down]
        .reshape(down, across, TILE, TILE, PIXEL_BYTES)
        .transpose(0, 2, 1, 3, 4)
    )
    return image


def padded_image(grid):
    """An empty padded frame (32 TY, 32 TX, 4) uint8 of `grid` (TX, TY)."""
    across, down = grid
    return np.empty((TILE * down, TILE * across, PIXEL_BYTES), dtype=np.uint8)


def copied_pages(frame_words, tiles, plane, first, across):
    """COPY's pages of the frame's words (tiles x planes pages of 1,024 words): plane
    `plane` of tile t, row-major, at page first + (t / 32) across + t mod 32;
    {page: words}."""
    planes = np.asarray(frame_words, dtype=np.uint32).reshape(-1, K["kPlanes"], 1024)
    out = {}
    for tile in range(tiles):
        page = first + tile // ROW_TILES * across + tile % ROW_TILES
        out[page] = planes[tile, plane][TILE_ORDER].reshape(-1)
    return out
