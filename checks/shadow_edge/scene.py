"""The written scene of the shadow edge's check: a floor, a plate above half of it, a
sun at an angle; the map, the lights a filter reads and the edge's closed form."""

import numpy as np

from prism_reference.direct.shadow import shadow_map
from prism_reference.scene.public.views import camera

F = np.float32
FLOOR_HALF = 10.0
PLATE = (2.0, 5.0)  # height, half depth; the plate covers x < 0
SUN = np.array([0.3, 1.0, 0.1]) / np.linalg.norm([0.3, 1.0, 0.1])  # toward the sun
ANGLE = 0.05  # the sun's diameter in radians
SIDE = 1024
BIAS_TEXELS = 3.0


def scene():
    """The floor and the plate as a scene dict a camera can view."""
    h, d = PLATE
    floor = [[-FLOOR_HALF, 0, -FLOOR_HALF], [FLOOR_HALF, 0, -FLOOR_HALF]]
    floor += [[FLOOR_HALF, 0, FLOOR_HALF], [-FLOOR_HALF, 0, FLOOR_HALF]]
    plate = [[-FLOOR_HALF, h, -d], [0, h, -d], [0, h, d], [-FLOOR_HALF, h, d]]
    indices = np.array([[0, 2, 1], [0, 3, 2], [4, 6, 5], [4, 7, 6]], np.int32)
    positions = np.array(floor + plate, np.float32)
    return {
        "positions": positions,
        "indices": indices,
        "colors": np.ones((len(positions), 3), np.float32),
        "camera": camera([3.0, 4.0, 6.0], [0.0, 0.0, 0.0], 50.0, 0.05),
        "light": np.zeros(3, np.float32),
        "eps": np.array([1e-4], np.float32),
    }


def materials(count):
    """The materials the traced share reads: one opaque material, no texture."""
    return {
        "material": np.zeros(count, np.int32),
        "kind": np.zeros(1, np.int32),
        "uv": np.zeros((count, 3, 2), np.float32),
        "textures": np.full((1, 4), -1, np.int32),
        "mip": np.zeros((0, 1, 3), np.int64),
        "texels": np.zeros(0, np.uint8),
    }


def lights(view):
    """The lights a filter reads: the sun's direction and its map at SIDE, the bias
    BIAS_TEXELS texels as 1/z."""
    depth, cam, texel = shadow_map(view, SUN.astype(np.float32), None, SIDE)
    distance = float(texel) * float(cam[12])
    return {
        "sun_direction": SUN.astype(np.float32),
        "shadow_map": depth,
        "shadow_camera": cam,
        "shadow_texel": texel,
        "shadow_bias": F(BIAS_TEXELS * float(texel) / distance**2),
        "shadow_side": np.int32(SIDE),
    }


def edge_x():
    """The floor's x where the plate's edge falls along the sun's direction."""
    return -PLATE[0] * SUN[0] / SUN[1]


def edge_share(x):
    """The share of the sun's disk a floor point at x (n,) sees past the edge: the
    disk cut by a straight line at the point's angular offset."""
    across = np.sqrt(1 - SUN[0] ** 2)
    reach = PLATE[0] / SUN[1]
    d = np.clip((x - edge_x()) * across / reach / np.tan(ANGLE / 2), -1, 1)
    return 1 - (np.arccos(d) - d * np.sqrt(1 - d * d)) / np.pi


def floor_points(count, seed=3):
    """Floor points (n, 3) across the edge, unit up normals, pixel numbers (n, 2)."""
    rng = np.random.default_rng(seed)
    width = PLATE[0] / SUN[1] * np.tan(ANGLE / 2) / np.sqrt(1 - SUN[0] ** 2)
    x = edge_x() + rng.uniform(-1.5, 1.5, count) * width
    z = rng.uniform(-2.0, 2.0, count)
    points = np.stack([x, np.zeros(count), z], 1).astype(np.float32)
    normals = np.tile(np.array([0, 1, 0], np.float32), (count, 1))
    pixels = rng.uniform(0, 1024, (count, 2)).astype(np.float32)
    return points, normals, pixels
