"""The fixed sample sets of the direct light: stratified points on an area light and
cosine-weighted directions for the world, the same for every pixel."""

import numpy as np

AREA_SIDE = 4  # AREA_SAMPLES = AREA_SIDE^2 cell centres
AREA_SAMPLES = AREA_SIDE * AREA_SIDE
WORLD_SIDE = 8  # WORLD_SAMPLES = WORLD_SIDE^2 cell centres
WORLD_SAMPLES = WORLD_SIDE * WORLD_SIDE


def cell_centres(side):
    """The centres (side^2, 2) of a side x side grid over the unit square."""
    k = (np.arange(side) + 0.5) / side
    a, b = np.meshgrid(k, k, indexing="ij")
    return np.stack([a.ravel(), b.ravel()], axis=1)


def concentric(square):
    """Shirley and Chiu's map of points (n, 2) of the unit square onto the unit disk,
    area preserving."""
    a, b = 2.0 * square[:, 0] - 1.0, 2.0 * square[:, 1] - 1.0
    first = np.abs(a) > np.abs(b)
    r = np.where(first, a, b)
    safe_a = np.where(a == 0, 1e-300, a)
    safe_b = np.where(b == 0, 1e-300, b)
    phi = np.where(
        first, (np.pi / 4) * b / safe_a, np.pi / 2 - (np.pi / 4) * a / safe_b
    )
    phi = np.where((a == 0) & (b == 0), 0.0, phi)
    return np.stack([r * np.cos(phi), r * np.sin(phi)], axis=1)


def area_points(round_shape):
    """AREA_SAMPLES points (n, 2) in [-1, 1]^2 (times the half axes u, v): the cell
    centres of the square, mapped onto the disk for a round shape."""
    square = cell_centres(AREA_SIDE)
    if round_shape:
        return concentric(square)
    return 2.0 * square - 1.0


def cosine_directions():
    """WORLD_SAMPLES directions (n, 3) about +z with density cos / pi: the cell centres
    (u1, u2) as r = sqrt(u1), phi = 2 pi u2, z = sqrt(1 - u1)."""
    cells = cell_centres(WORLD_SIDE)
    r, phi = np.sqrt(cells[:, 0]), 2.0 * np.pi * cells[:, 1]
    z = np.sqrt(np.maximum(1.0 - cells[:, 0], 0.0))
    return np.stack([r * np.cos(phi), r * np.sin(phi), z], axis=1)


def frames(n):
    """Unit tangents t and bitangents b (n, 3) with (t, b, n) right-handed."""
    helper = np.where(
        (np.abs(n[:, 0]) < 0.9)[:, None], [[1.0, 0.0, 0.0]], [[0.0, 1.0, 0.0]]
    )
    t = np.cross(helper, n)
    t /= np.linalg.norm(t, axis=1, keepdims=True)
    return t, np.cross(n, t)
