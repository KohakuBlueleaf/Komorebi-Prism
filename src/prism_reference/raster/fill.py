"""Binning the records to tiles and the fill of one tile: the top-left rule, the larger
1/z wins, a tie to the lower triangle number."""

import numpy as np

from prism_reference.scene.frame import HEIGHT, TILE, WIDTH

# The default frame's grid (a scene's `size` entry chooses another: setup.grid).
TILES_X = WIDTH // TILE
TILES_Y = HEIGHT // TILE
BACKGROUND = np.array([0.05, 0.05, 0.08], dtype=np.float32)
CHUNK = 128
F = np.float32


def bin_triangles(records, tiles_x=TILES_X, tiles_y=TILES_Y):
    """Tile lists: (counts per tile, offsets (tiles + 1), record numbers by tile);
    tile ty tiles_x + tx of a grid of tiles_x by tiles_y."""
    box = records["box"]
    tx0, tx1 = box[:, 0] // TILE, box[:, 1] // TILE
    ty0, ty1 = box[:, 2] // TILE, box[:, 3] // TILE
    nx, ny = tx1 - tx0 + 1, ty1 - ty0 + 1
    per_tri = nx * ny
    total = int(per_tri.sum())
    rec = np.repeat(np.arange(len(box)), per_tri)
    start = np.cumsum(per_tri) - per_tri
    local = np.arange(total) - np.repeat(start, per_tri)
    tile = (ty0[rec] + local // nx[rec]) * tiles_x + tx0[rec] + local % nx[rec]
    order = np.argsort(tile, kind="stable")
    counts = np.bincount(tile, minlength=tiles_x * tiles_y).astype(np.int32)
    offsets = np.concatenate([[0], np.cumsum(counts)]).astype(np.int64)
    return counts, offsets, rec[order].astype(np.int32)


def fill_tile(records, members, tx, ty):
    """Colour (32, 32, 3), 1/z and record number (-1: none) of one tile."""
    px = (F(tx * TILE) + np.arange(TILE, dtype=np.float32) + F(0.5))[None, None, :]
    py = (F(ty * TILE) + np.arange(TILE, dtype=np.float32) + F(0.5))[None, :, None]
    cols = (np.arange(TILE) + tx * TILE)[None, None, :]
    rows = (np.arange(TILE) + ty * TILE)[None, :, None]
    depth = np.zeros((TILE, TILE), dtype=np.float32)
    winner = np.full((TILE, TILE), -1, dtype=np.int64)
    colour = np.empty((TILE, TILE, 3), dtype=np.float32)
    colour[:] = BACKGROUND
    if len(members) == 0:
        return colour, depth, winner
    for s in range(0, len(members), CHUNK):
        m = members[s : s + CHUNK]
        a, b, c = (records[k][m][:, :, None, None] for k in ("a", "b", "c"))
        tl = records["top_left"][m][:, :, None, None]
        e = (a * px[:, None] + b * py[:, None]) + c
        inside = ((e > 0) | ((e == 0) & tl)).all(axis=1)
        box = records["box"][m]
        inside &= (cols >= box[:, 0, None, None]) & (cols <= box[:, 1, None, None])
        inside &= (rows >= box[:, 2, None, None]) & (rows <= box[:, 3, None, None])
        wp = records["w_planes"][m]
        w = (wp[:, 0, None, None] * px + wp[:, 1, None, None] * py) + wp[
            :, 2, None, None
        ]
        w = np.where(inside, w, F(-np.inf))
        first = w.argmax(axis=0)
        best = np.take_along_axis(w, first[None], axis=0)[0]
        better = best > depth
        depth = np.where(better, best, depth)
        winner = np.where(better, m[first], winner)
    hit = winner >= 0
    cp = records["c_planes"][np.where(hit, winner, 0)]
    shade = (
        cp[:, :, 0] * px[0, 0, :, None] + cp[:, :, 1] * py[0, :, 0, None, None]
    ) + cp[:, :, 2]
    colour[hit] = shade[hit]
    return colour, depth, winner
