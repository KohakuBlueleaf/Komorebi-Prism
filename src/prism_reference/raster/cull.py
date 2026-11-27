"""The walk's cull: a group of triangle blocks whose box lies wholly outside a view's
frustum (behind its near distance or past an edge of its padded frame) holds no triangle
that can reach a pixel, and is not walked."""

import numpy as np

from prism_reference.scene.frame import TILE

F = np.float32
LANES = 32  # triangles a block
SLACK = F(1e-5)  # the box's margin, of the camera-space magnitudes it is made from


def block_boxes(positions, indices):
    """(blocks, 2, 3) float32: each block of LANES triangles' least and most corner
    (indices (T, 3) in block order; a block's padding is no triangle)."""
    count = len(indices)
    blocks = -(-count // LANES)
    padded = np.concatenate(
        [indices, np.repeat(indices[-1:], blocks * LANES - count, axis=0)]
    )
    out = np.empty((blocks, 2, 3), dtype=F)
    step = 1 << 14  # blocks at a time
    for first in range(0, blocks, step):
        end = min(blocks, first + step)
        corners = positions[padded[first * LANES : end * LANES]]
        corners = corners.reshape(end - first, 3 * LANES, 3)
        out[first:end, 0] = corners.min(axis=1)
        out[first:end, 1] = corners.max(axis=1)
    return out


def group_boxes(boxes, group):
    """(groups, 2, 3) float32: the boxes of `group` consecutive blocks each (the last
    group what is left)."""
    count = len(boxes)
    groups = -(-count // group)
    pad = groups * group - count
    least = np.concatenate([boxes[:, 0], np.full((pad, 3), np.inf, dtype=F)])
    most = np.concatenate([boxes[:, 1], np.full((pad, 3), -np.inf, dtype=F)])
    least = least.reshape(groups, group, 3).min(axis=1)
    most = most.reshape(groups, group, 3).max(axis=1)
    return np.stack([least, most], axis=1).astype(F)


def camera_box(camera, boxes):
    """Each box's camera-space bounds ((G, 3) least, (G, 3) most) float32: its centre
    along the camera's rows, its half sizes along their magnitudes, widened by SLACK of
    the magnitudes."""
    least, most = boxes[:, 0].astype(F), boxes[:, 1].astype(F)
    half = F(0.5)
    centre = (least + most) * half
    size = (most - least) * half
    d = centre - camera[0:3]
    scale = (np.abs(d[:, 0]) + np.abs(d[:, 1])) + np.abs(d[:, 2])
    scale = scale + ((size[:, 0] + size[:, 1]) + size[:, 2])
    low, high = [], []
    for row in range(3):
        r = camera[3 + 3 * row : 6 + 3 * row]
        at = (d[:, 0] * r[0] + d[:, 1] * r[1]) + d[:, 2] * r[2]
        reach = (size[:, 0] * abs(r[0]) + size[:, 1] * abs(r[1])) + size[:, 2] * abs(
            r[2]
        )
        reach = reach + scale * SLACK
        low.append(at - reach)
        high.append(at + reach)
    return np.stack(low, axis=1), np.stack(high, axis=1)


def most_of(a, low, high):
    """The most of a times a value in [low, high]."""
    return np.where(a >= 0, a * high, a * low)


def outside(camera, boxes, grid):
    """(G,) bool: the boxes wholly behind the near distance (camera[15]) or past an edge
    of the padded frame of `grid` (across, down tiles) for every point in front of it.
    """
    low, high = camera_box(camera, boxes)
    focal, cx, cy, near = camera[12], camera[13], camera[14], camera[15]
    width, height = F(TILE * grid[0]), F(TILE * grid[1])
    behind = high[:, 2] < near
    left = focal * high[:, 0] + most_of(cx, low[:, 2], high[:, 2]) < 0
    right = -focal * low[:, 0] + most_of(width - cx, low[:, 2], high[:, 2]) < 0
    top = most_of(cy, low[:, 2], high[:, 2]) - focal * low[:, 1] < 0
    bottom = focal * high[:, 1] + most_of(height - cy, low[:, 2], high[:, 2]) < 0
    return behind | left | right | top | bottom
