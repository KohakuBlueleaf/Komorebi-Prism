"""The sun's cascade: maps fitted to slices of a view's frustum, the scene's whole-box
map beyond them, and the lookup through the finest map that holds a point."""

import itertools

import numpy as np

from prism_reference.direct.shadow import SUN_DISTANCE, map_at, sun_screen
from prism_reference.direct.shadow_filter import filtered_shadow, sun_map
from prism_reference.scene.frame import frame_size

F = np.float32
# The practical split's share of the logarithmic split.
SPLIT_LOG = 0.75


def view_reach(view):
    """The nearest and farthest distances along the view's forward axis that the
    scene's box spans (the near one at least the camera's near distance)."""
    cam = view["camera"].astype(np.float64)
    p = view["positions"]
    lo, hi = p.min(0).astype(np.float64), p.max(0).astype(np.float64)
    box = np.stack(np.meshgrid(*zip(lo, hi), indexing="ij"), -1).reshape(-1, 3)
    along = (box - cam[0:3]) @ cam[9:12]
    near = float(cam[15])
    return near, max(float(along.max()), near * 2)


def seen_reach(depth):
    """The nearest and farthest distances along the view's forward axis of a frame's
    covered pixels, from its 1/z (H, W) (0: empty)."""
    seen = depth[depth > 0]
    return float(1 / seen.max()), float(1 / seen.min())


def splits(near, far, count, share=SPLIT_LOG):
    """count + 1 distances from near to far: the practical split (a share of the
    logarithmic split, the rest uniform)."""
    k = np.arange(count + 1) / count
    log = near * (far / near) ** k
    return share * log + (1 - share) * (near + (far - near) * k)


def slice_corners(view, start, end):
    """The 8 corners (8, 3) of the view's frustum between distances start and end."""
    cam = view["camera"].astype(np.float64)
    width, height = frame_size(view)
    out = []
    for d in (start, end):
        for x in (0.0, float(width)):
            for y in (0.0, float(height)):
                a, b = (x - cam[13]) / cam[12], (cam[14] - y) / cam[12]
                out.append(cam[0:3] + d * (cam[9:12] + a * cam[3:6] + b * cam[6:9]))
    return np.array(out)


def fitted_camera(positions, sun, corners, side):
    """A sun camera (16,) float32 of side x side whose frame covers the corners'
    extent across the sun, cut to the scene box's, at SUN_DISTANCE radii (as
    `sun_camera`, the same axes)."""
    lo, hi = positions.min(0).astype(np.float64), positions.max(0).astype(np.float64)
    centre, radius = (lo + hi) / 2, np.linalg.norm(hi - lo) / 2
    distance = SUN_DISTANCE * radius
    fwd = -np.asarray(sun, np.float64)
    helper = np.array([0.0, 1.0, 0.0]) if abs(fwd[1]) < 0.99 else np.array([1, 0, 0])
    right = np.cross(helper, fwd)
    right /= np.linalg.norm(right)
    up = np.cross(fwd, right)
    box = np.stack(np.meshgrid(*zip(lo, hi), indexing="ij"), -1).reshape(-1, 3)
    axes = np.stack([right, up])
    box_span = (box - centre) @ axes.T
    span = (corners - centre) @ axes.T
    low = np.maximum(span.min(0), box_span.min(0))
    high = np.minimum(span.max(0), box_span.max(0))
    high = np.maximum(high, low)
    middle = (low + high) / 2
    half = max(float((high - low).max()) / 2, 1e-6 * radius)
    half = half * side / (side - 2)
    target = centre + middle @ axes
    focal = (side / 2) * (distance - radius) / half
    eye = target - fwd * distance
    tail = [focal, side / 2, side / 2, distance - 2 * radius]
    return np.concatenate([eye, right, up, fwd, tail]).astype(np.float32)


def cascade_cameras(view, sun, count, side, reach=None):
    """The cameras of `count` maps fitted to the practical split of `reach` (near, far;
    None: `view_reach`), finest first, and the split distances (count + 2)."""
    near, far = reach or view_reach(view)
    cuts = splits(near, far, count + 1)
    cameras = [
        fitted_camera(view["positions"], sun, slice_corners(view, a, b), side)
        for a, b in itertools.pairwise(cuts[:-1])
    ]
    return cameras, cuts


def cascade_maps(view, materials, lights, count, side, reach=None):
    """The cascade's maps as filters read them (`sun_map`'s keys), finest first, then
    the lights' whole-box map; each map's bias is the lights' in texels; reach as
    `cascade_cameras`."""
    whole = sun_map(lights)
    centre = (view["positions"].min(0) + view["positions"].max(0)) / 2
    distance = float(np.linalg.norm(lights["shadow_camera"][0:3] - centre))
    texels = float(lights["shadow_bias"]) * distance**2 / float(lights["shadow_texel"])
    cameras, _ = cascade_cameras(view, lights["sun_direction"], count, side, reach)
    maps = []
    for camera in cameras:
        texel = F(distance / camera[12])
        maps.append(
            {
                "depth": map_at(view, camera, materials, side),
                "camera": camera,
                "texel": texel,
                "bias": F(texels * float(texel) / distance**2),
            }
        )
    return [*maps, whole]


def cascade_choice(maps, points, normals, margin):
    """Per point the index of the finest map whose frame holds it `margin` texels in
    from its edge (the last map where none does)."""
    choice = np.full(len(points), len(maps) - 1, dtype=np.int64)
    for k in range(len(maps) - 2, -1, -1):
        sx, sy, _ = sun_screen(maps[k]["camera"], maps[k]["texel"], points, normals)
        side = maps[k]["depth"].shape[0]
        inside = (sx >= margin) & (sx < side - margin)
        inside &= (sy >= margin) & (sy < side - margin)
        choice = np.where(inside, k, choice)
    return choice


def cascade_shadow(maps, points, normals, method, pixels=None, margin=4):
    """Sun share (n,) through the finest map holding each point (`cascade_choice`),
    filtered by `method` (`filtered_shadow`), and the choice."""
    choice = cascade_choice(maps, points, normals, margin)
    share = np.ones(len(points), dtype=np.float32)
    for k, smap in enumerate(maps):
        take = choice == k
        if take.any():
            pick = None if pixels is None else pixels[take]
            share[take] = filtered_shadow(
                smap, points[take], normals[take], method, pick
            )
    return share, choice
