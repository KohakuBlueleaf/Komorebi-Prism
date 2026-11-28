"""The near field fused with the field: the near operator applied to a radiance image, the
depth- and normal-aware filter of its two outputs, the rule, and the bounces."""

import numpy as np

from prism_reference.indirect.near.march import march
from prism_reference.indirect.near.screen import (
    camera_axes,
    camera_space,
    coarse_depth,
    coarse_radiance,
)

F = np.float32
# The rule's knobs in units of the field's element spacing h, and the filter's.
RULE = {
    "near_range": 2.0,
    "thickness": 0.5,
    "coarse_cap": 1.0,
    "filter": 2,
    "plane": 0.05,
}
RULE["backface"] = 2
RULE["facing"] = 0
FLOOR_K = 0.01


def near_frame(camera, position, normal, geometric, covered, level):
    """What the march reads: camera-space points, shading and geometric normals, depth,
    the coarse copy."""
    p, n, z = camera_space(camera, position, normal, covered)
    _, axes, focal, cx, cy = camera_axes(camera)
    near, far, nearest = coarse_depth(z, p, level)
    frame = {"point": p, "normal": n, "depth": z, "focal": focal, "cx": cx, "cy": cy}
    frame["geometric"] = geometric.astype(np.float64) @ axes
    frame["camera"] = np.asarray(camera, np.float64)
    return frame | {"coarse_near": near, "coarse_far": far, "coarse_point": nearest}


def previous_frame(camera, frame):
    """The previous frame (its `near_frame`, with its own camera in it) as the march
    reads it for the current `camera`: its axes turned into the current camera's."""
    eye, axes, _, _, _ = camera_axes(camera)
    old_eye, old_axes, _, _, _ = camera_axes(frame["camera"])
    turn = axes.T @ old_axes
    return {"frame": frame, "rotation": turn, "offset": (old_eye - eye) @ axes}


def near_operator(
    frame, receivers, spacing, rule=None, settings=None, log=None, workers=1
):
    """The near operator (`march`, by `workers` processes) with the rule's ranges in
    world units."""
    rule = {**RULE, **(rule or {})}
    r, t = rule["near_range"] * spacing, rule["thickness"] * spacing
    ranges = {"near": r, "thickness": t, "cap": rule["coarse_cap"] * t}
    op = march(
        frame,
        receivers,
        ranges | {k: rule[k] for k in ("plane", "backface", "facing")},
        settings,
        log,
        workers,
    )
    return op | {"rule": rule}


def source_table(frame, radiance, behind, level):
    """A frame's sources (rows, 3): its pixels, its coarse cells, then its pixels seen
    from behind in reverse (a source -1 - pixel)."""
    coarse = coarse_radiance(radiance, frame["depth"], level)
    behind = radiance if behind is None else behind
    table = np.concatenate([radiance.reshape(-1, 3), coarse.reshape(-1, 3)])
    return np.concatenate([table, behind.reshape(-1, 3)[::-1]])


def near_radiance(op, frame, radiance, behind=None, previous=None):
    """The radiance the near hits bring (H, W, 3): sum of weight x the source's radiance
    (a pixel's, the coarse copy's cell mean, or `behind`'s for a pixel seen from behind);
    entries of levels 2 and 3 take theirs from `previous` (frame, radiance, behind)."""
    z = frame["depth"]
    h, w = z.shape
    level = op["settings"]["coarse_level"]
    table = source_table(frame, radiance, behind, level)
    picked = np.zeros((len(op["source"]), 3))
    now = op["level"] < 2
    picked[now] = table[op["source"][now]]
    if previous is not None:
        old = source_table(*previous, level)
        picked[~now] = old[op["source"][~now]]
    picked = picked * op["weight"][:, None]
    out = [np.bincount(op["pixel"], picked[:, c], h * w) for c in range(3)]
    return np.stack(out, -1).reshape(h, w, 3)


def smooth(images, frame, radius, tile=0, label=None):
    """Each image (H, W, ...) averaged over the (2 radius + 1)^2 window with weights from
    depth (relative difference) and normal agreement; uncovered pixels take no part, nor
    (tile > 0) pixels of another tile, nor pixels of another `label` (H, W) when given.
    """
    if radius <= 0:
        return images
    z, n = frame["depth"], frame["normal"]
    covered = np.isfinite(z)
    h, w = z.shape
    gy, gx = np.mgrid[0:h, 0:w]
    tile_of = (gy // tile) * w + gx // tile if tile > 0 else np.zeros((h, w), int)
    tile_of = tile_of if label is None else label
    zc = np.where(covered, z, 1.0)
    pad = radius
    zp = np.pad(zc, pad, mode="edge")
    cp = np.pad(covered, pad)
    np_ = np.pad(n, ((pad, pad), (pad, pad), (0, 0)), mode="edge")
    tp = np.pad(tile_of, pad, constant_values=-1)
    padded = [
        np.pad(a, [(pad, pad), (pad, pad)] + [(0, 0)] * (a.ndim - 2)) for a in images
    ]
    sums = [np.zeros_like(a) for a in images]
    total = np.zeros((h, w))
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            win = (slice(pad + dy, pad + dy + h), slice(pad + dx, pad + dx + w))
            rel = (zp[win] - zc) / (0.02 * zc)
            agree = np.maximum((np_[win] * n).sum(-1), 0.0) ** 8
            wt = np.exp(-rel * rel) * agree * cp[win] * covered
            wt = wt * (tp[win] == tile_of)
            total += wt
            for s, a in zip(sums, padded):
                s += a[win] * (wt if a.ndim == 2 else wt[..., None])
    norm = np.maximum(total, 1e-30)
    return [
        np.where(
            covered if a.ndim == 2 else covered[..., None],
            s / (norm if a.ndim == 2 else norm[..., None]),
            a,
        )
        for s, a in zip(sums, images)
    ]


def fused(near, blocked, e_far, k):
    """The rule: E = pi (near + (1 - blocked) Lfar), Lfar = E_far / (pi K); where K is
    under FLOOR_K, Lfar is the near hits' mean radiance (E_far / pi without hits)."""
    low = k < FLOOR_K
    hits = near / np.maximum(blocked, 1e-30)[..., None]
    own = np.where((blocked > 0)[..., None], hits, e_far / np.pi)
    lfar = np.where(low, own, e_far / (np.pi * np.maximum(k, FLOOR_K)))
    return np.pi * (near + (1.0 - blocked)[..., None] * lfar)


def bounces(op, frame, direct_out, albedo, e_far, k, tile=0):
    """Two bounces: E1 from the near hits of the direct light and the field at one bounce
    (e_far[1]); E2 from the direct light plus albedo / pi E1 and the field at two."""
    radius = op["rule"]["filter"]
    blocked = op["blocked"].reshape(frame["depth"].shape)
    out = []
    source, indirect = direct_out, np.zeros_like(direct_out)
    for b in (1, 2):
        near = near_radiance(op, frame, source, indirect)
        near, blk = smooth([near, blocked], frame, radius, tile)
        e = fused(near, blk, e_far[b], k)
        out.append(e)
        indirect = albedo / np.pi * e
        source = direct_out + indirect
    return out


def one_apply(op, frame, direct_out, albedo, e_last, e_far, k, previous=None, tile=0):
    """One bounce a frame: the near hits of the direct light plus albedo / pi e_last (the
    last frame's E), fused with the field e_far; `previous` as in `near_radiance`."""
    blocked = op["blocked"].reshape(frame["depth"].shape)
    indirect = albedo / np.pi * e_last
    near = near_radiance(op, frame, direct_out + indirect, indirect, previous)
    near, blk = smooth([near, blocked], frame, op["rule"]["filter"], tile)
    return fused(near, blk, e_far, k)
