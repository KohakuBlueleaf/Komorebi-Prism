"""The written scene: a box standing on a floor, a camera in front of the box's face,
rasterized; each pixel's point, normal and distance from the box's face along the floor.
"""

import numpy as np

from prism_reference.raster.frames import picture, rasterize
from prism_reference.raster.setup import world_points
from prism_reference.scene.public.views import camera

F = np.float32
SIZE = (192, 192)
FLOOR_HALF = 12.0
BOX_HALF = 1.0
SPACING = 0.5  # the field's element spacing h the rule is scaled by
EYE, TARGET, FOV = (0.0, 2.5, 6.0), (0.0, 0.3, 1.0), 60.0


def quad(corners):
    """Four corners (4, 3) in order as two triangles (2, 3) of indices from 0."""
    return np.asarray(corners, np.float64), np.array([[0, 1, 2], [0, 2, 3]], np.int32)


def geometry():
    """The floor and the box's five faces as positions (V, 3) and indices (T, 3)."""
    f, b = FLOOR_HALF, BOX_HALF
    faces = [[(-f, 0, -f), (f, 0, -f), (f, 0, f), (-f, 0, f)]]
    faces.append([(-b, 2 * b, -b), (b, 2 * b, -b), (b, 2 * b, b), (-b, 2 * b, b)])
    for s in (-b, b):
        faces.append([(-b, 0, s), (b, 0, s), (b, 2 * b, s), (-b, 2 * b, s)])
        faces.append([(s, 0, -b), (s, 0, b), (s, 2 * b, b), (s, 2 * b, -b)])
    positions, indices = [], []
    for k, corners in enumerate(faces):
        p, i = quad(corners)
        positions.append(p)
        indices.append(i + 4 * k)
    return np.concatenate(positions), np.concatenate(indices)


def frame():
    """The rasterized frame: camera, covered (H, W), point, normal (H, W, 3) facing the
    eye, the floor's mask and each pixel's distance in front of the box's face."""
    positions, indices = geometry()
    cam = camera(EYE, TARGET, FOV, 0.01)
    cam[12] = F(cam[12] * max(SIZE) / 1024)
    cam[13], cam[14] = F(SIZE[0] / 2), F(SIZE[1] / 2)
    scene = {
        "positions": positions.astype(F),
        "colors": np.ones_like(positions, F),
        "indices": indices,
        "camera": cam,
        "eps": np.array([1e-4], F),
        "size": SIZE,
    }
    out = rasterize(scene)
    tri = picture(out["tri"], scene)
    depth = picture(out["depth"], scene)
    covered = tri >= 0
    ys, xs = np.nonzero(covered)
    point = np.zeros(tri.shape + (3,), F)
    point[ys, xs] = world_points(cam, xs + F(0.5), ys + F(0.5), depth[ys, xs])
    v = positions[indices]
    n = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    normal = np.zeros_like(point)
    normal[ys, xs] = n[tri[ys, xs]]
    toward = ((np.asarray(EYE, F) - point) * normal).sum(-1) < 0
    normal = np.where(toward[..., None], -normal, normal)
    floor = covered & (tri < 2)
    ahead = np.where(floor, point[..., 2] - BOX_HALF, -1.0)
    ahead = np.where(np.abs(point[..., 0]) < 0.6 * BOX_HALF, ahead, -1.0)
    return {
        "camera": cam,
        "covered": covered,
        "point": point,
        "normal": normal,
        "floor": floor,
        "ahead": ahead,
    }
