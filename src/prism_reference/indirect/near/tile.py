"""The near field as columns of one screen tile's product: a fixed pattern of coarse
colour cells around the tile, the march's bits credited to the cell a sample falls in,
and the cells' mean radiance as the shared operand."""

import numpy as np

# The tile's cells across, the rings of 8 cells around it (each ring's cells 3 x the
# last ring's), the treatment of samples seen from behind (0, 1, 2 as `fuse.RULE`).
PATTERN = {"split": 2, "rings": 2, "backface": 0}


def pattern_cells(tile, split, rings):
    """The pattern's cells (n, 4) as (x0, y0, x1, y1) in pixels from the tile's corner:
    the tile in split x split cells, then each ring's 8 cells around the square so far.
    """
    s = tile // split
    cells = [
        (j * s, i * s, (j + 1) * s, (i + 1) * s)
        for i in range(split)
        for j in range(split)
    ]
    low, size = 0, tile
    for _ in range(rings):
        low -= size
        for i in range(3):
            for j in range(3):
                if (i, j) != (1, 1):
                    x0, y0 = low + j * size, low + i * size
                    cells.append((x0, y0, x0 + size, y0 + size))
        size *= 3
    return np.array(cells, np.int64)


def cell_of(cells, dx, dy):
    """The pattern cell (n,) holding each offset (dx, dy) from the tile's corner, -1
    outside the pattern."""
    out = np.full(len(dx), -1, np.int64)
    for c, (x0, y0, x1, y1) in enumerate(cells):
        out[(dx >= x0) & (dx < x1) & (dy >= y0) & (dy < y1)] = c
    return out


def sample_places(op, shape):
    """Each entry's source as a screen place (n, 2) (x, y, pixel centres) and whether it
    is a pixel seen from behind."""
    h, w = shape
    src = op["source"].astype(np.int64)
    level = op["settings"]["coarse_level"]
    behind = src < 0
    pixel = np.where(behind, -1 - src, src)
    coarse = pixel >= h * w
    cell = pixel - h * w
    wc = -(-w >> level)
    s = 1 << level
    x = np.where(coarse, (cell % wc + 0.5) * s, pixel % w + 0.5)
    y = np.where(coarse, (cell // wc + 0.5) * s, pixel // w + 0.5)
    return np.stack([x, y], 1), behind


def near_weights(op, shape, tile, pattern=None, owner=None):
    """W_near (H, W, columns) of every receiver on its tile's pattern cells (or on those
    of the tile `owner` (ty, tx; (H, W) each) names): the weight of the entries whose
    sample lies in a cell; backface 2 adds the behind columns, 1 drops them."""
    pattern = {**PATTERN, **(pattern or {})}
    h, w = shape
    cells = pattern_cells(tile, pattern["split"], pattern["rings"])
    place, behind = sample_places(op, shape)
    pixel = op["pixel"].astype(np.int64)
    if owner is None:
        corner = np.stack([pixel % w // tile * tile, pixel // w // tile * tile], 1)
    else:
        ty, tx = (o.reshape(-1)[pixel] for o in owner)
        corner = np.stack([tx * tile, ty * tile], 1)
    rel = place - corner
    cell = cell_of(cells, rel[:, 0], rel[:, 1])
    weight = op["weight"]
    columns = len(cells) * (2 if pattern["backface"] == 2 else 1)
    if pattern["backface"] == 1:
        cell = np.where(behind, -1, cell)
    if pattern["backface"] == 2:
        cell = np.where(behind & (cell >= 0), cell + len(cells), cell)
    keep = cell >= 0
    flat = np.bincount(
        pixel[keep] * columns + cell[keep], weight[keep], h * w * columns
    )
    return flat.reshape(h, w, columns)


def summed(image):
    """The summed-area table (H + 1, W + 1, ...) of an image."""
    out = np.zeros((image.shape[0] + 1, image.shape[1] + 1) + image.shape[2:])
    out[1:, 1:] = image.cumsum(0).cumsum(1)
    return out


def cell_values(radiance, covered, tile, pattern=None, behind=None):
    """S_near (tiles down, tiles across, columns, 3): each tile's pattern cells' mean
    radiance over covered pixels (0 where none); backface 2: then `behind`'s."""
    pattern = {**PATTERN, **(pattern or {})}
    h, w = covered.shape
    cells = pattern_cells(tile, pattern["split"], pattern["rings"])
    images = [radiance] + ([behind] if pattern["backface"] == 2 else [])
    count = summed(covered.astype(np.float64))
    ty, tx = -(-h // tile), -(-w // tile)
    oy, ox = np.mgrid[0:ty, 0:tx] * tile
    out = []
    for image in images:
        total = summed(image.astype(np.float64) * covered[..., None])
        for x0, y0, x1, y1 in cells:
            a0, a1 = np.clip(ox + x0, 0, w), np.clip(ox + x1, 0, w)
            b0, b1 = np.clip(oy + y0, 0, h), np.clip(oy + y1, 0, h)
            n = count[b1, a1] - count[b0, a1] - count[b1, a0] + count[b0, a0]
            s = total[b1, a1] - total[b0, a1] - total[b1, a0] + total[b0, a0]
            out.append(s / np.maximum(n, 1)[..., None])
    return np.stack(out, 2)
