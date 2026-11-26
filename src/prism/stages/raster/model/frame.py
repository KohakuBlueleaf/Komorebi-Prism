"""The frame's pages: per tile five planes in the destination register's window order."""

import numpy as np

from prism.stages.raster.model.cost import as_item
from prism.stages.raster.model.numbers import TILES, K
from prism.stages.raster.model.records import triangle_numbers, triangle_words
from prism_reference.raster.fill import TILES_X, TILES_Y
from prism_reference.scene.frame import HEIGHT, WIDTH


def window_index(rows, lanes):
    """Word of (vector `rows`, lane `lanes`) in a plane read out of the Dst window."""
    rows, lanes = np.asarray(rows), np.asarray(lanes)
    return 64 * (rows // 2) + 16 * (lanes >> 3) + 2 * (lanes & 7) + rows % 2


ROW, COL = np.meshgrid(np.arange(32), np.arange(32), indexing="ij")
TILE_ORDER = window_index(ROW, COL)  # (32, 32): word of pixel (row, col)


def decode_frame(frame):
    """Colour, depth and triangle images from the frame pages (tiles x 5, 1024)."""
    planes = np.asarray(frame, dtype=np.uint32).reshape(TILES, K["kPlanes"], 1024)
    pixels = planes[:, :, TILE_ORDER].view(np.float32)  # (tiles, plane, 32, 32)
    pixels = pixels.reshape(TILES_Y, TILES_X, K["kPlanes"], 32, 32)
    image = pixels.transpose(2, 0, 3, 1, 4).reshape(K["kPlanes"], HEIGHT, WIDTH)
    triangle = triangle_numbers(image[4].view(np.uint32))
    return {
        "colour": np.ascontiguousarray(np.stack(image[1:4], axis=2)),
        "depth": np.ascontiguousarray(image[0]),
        "tri": triangle.astype(np.int32),
    }


def decoded(words, across, down):
    """Depth, colour and triangle images of the frame's pages (tile slot = tile)."""
    tiles = across * down
    planes = words.reshape(-1, K["kPlanes"], 1024)[:tiles]
    pixels = planes[:, :, TILE_ORDER].view(np.float32)
    pixels = pixels.reshape(down, across, K["kPlanes"], 32, 32)
    return pixels.transpose(2, 0, 3, 1, 4).reshape(K["kPlanes"], 32 * down, 32 * across)


def frame_of(images):
    """The frame pages the card would write for these images (inverse of decode)."""
    image = np.stack(
        [
            images["depth"],
            *np.moveaxis(images["colour"], 2, 0),
            triangle_words(images["tri"]).view(np.float32),
        ]
    ).astype(np.float32)
    pixels = image.reshape(K["kPlanes"], TILES_Y, 32, TILES_X, 32)
    pixels = pixels.transpose(1, 3, 0, 2, 4).reshape(TILES, K["kPlanes"], 32, 32)
    frame = np.zeros((TILES, K["kPlanes"], 1024), dtype=np.uint32)
    frame[:, :, TILE_ORDER] = pixels.view(np.uint32)
    return frame.reshape(TILES * K["kPlanes"], 1024)


def busy_map(tiles_of, busy):
    """Per-pixel image of each core's busy cycles over the tiles it owns."""
    per_tile = np.zeros(TILES)
    for core, tiles in enumerate(tiles_of):
        for item in tiles:
            tile = as_item(item)[0]
            per_tile[tile] = max(per_tile[tile], busy[core])
    grid = per_tile.reshape(TILES_Y, TILES_X)
    return np.repeat(np.repeat(grid, 32, axis=0), 32, axis=1)
