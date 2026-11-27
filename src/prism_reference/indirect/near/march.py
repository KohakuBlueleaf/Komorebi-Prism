"""The near field's march: per pixel, slices of the screen in two levels (full resolution
within the tile's halo, the coarse copy beyond), each sample covering bits of the
cosine measure; the result is a sparse operator from the frame's radiance to the pixels.
"""

import numpy as np

from prism_reference.indirect.near.measure import (
    BITS,
    bit_range,
    side_share,
    side_total,
    slice_frame,
)

TILE = 32
# The 4 x 4 pattern that rotates a pixel's slices and offsets its steps.
PATTERN = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16
SETTINGS = {
    "slices": 4,
    "short_steps": 8,
    "long_steps": 8,
    "halo": 16,
    "coarse_level": 3,
    "reach_px": 512,
}


def side_angle(delta, v, d, side):
    """A sample's angle (n,) in [0, pi] from V toward side x Dp, in the slice."""
    a = np.arctan2(side * (delta * d).sum(1), (delta * v).sum(1))
    return np.clip(a, 0.0, np.pi)


def step_radius(j, settings, jitter, short_end, long_end):
    """Step j's screen distance (n,) and whether it is active: short steps squared-spaced
    over [1, short_end], long ones over (halo, long_end]."""
    s1, s2, halo = settings["short_steps"], settings["long_steps"], settings["halo"]
    if j < s1:
        f = ((j + jitter) / s1) ** 2
        return 1.0 + (short_end - 1.0) * f, short_end >= 1.0
    f = ((j - s1 + jitter) / s2) ** 2
    return halo + (long_end - halo) * f, long_end > halo


def sample(frame, settings, short, sx, sy, thickness, cap):
    """A step's sample at screen (sx, sy) (n,) each: front and back points (n, 3), the
    source index (n,) (pixel, or H W + coarse cell), whether it holds a surface, its
    pixel and its normal (None on the coarse copy)."""
    z = frame["depth"]
    h, w = z.shape
    ix = np.clip(np.floor(sx), 0, w - 1).astype(np.int64)
    iy = np.clip(np.floor(sy), 0, h - 1).astype(np.int64)
    if short:
        zq = z[iy, ix]
        valid = np.isfinite(zq)
        q = frame["point"][iy, ix]
        back = zq + thickness
        src = iy * w + ix
        facing = frame["normal"][iy, ix]
    else:
        c = settings["coarse_level"]
        cy, cx = iy >> c, ix >> c
        zq = frame["coarse_near"][cy, cx]
        far = frame["coarse_far"][cy, cx]
        valid = np.isfinite(zq)
        zq = np.where(valid, zq, 1.0)
        q = frame["coarse_point"][cy, cx]
        back = np.maximum(zq + thickness, np.minimum(far, zq + cap))
        src = h * w + cy * frame["coarse_near"].shape[1] + cx
        facing = None
    zs = np.where(valid, zq, 1.0)
    qb = q * (np.where(valid, back, 1.0) / zs)[:, None]
    return q, qb, src, valid, iy, ix, facing


def march_rows(frame, receivers, y0, ranges, settings):
    """The march of the receivers in rows [y0, y0 + TILE): entries (pixel, source,
    weight, level) and the reads of each level."""
    z = frame["depth"]
    h, w = z.shape
    ys, xs = np.nonzero(receivers[y0 : y0 + TILE])
    ys = ys + y0
    pixel = ys * w + xs
    p, n = frame["point"][ys, xs], frame["normal"][ys, xs]
    geo = frame["geometric"][ys, xs]
    near_range, thickness, cap = ranges["near"], ranges["thickness"], ranges["cap"]
    rot, jitter = PATTERN[ys % 4, xs % 4], PATTERN.T[ys % 4, xs % 4]
    reach = near_range * frame["focal"] / p[:, 2]
    short_end = np.minimum(reach, settings["halo"])
    long_end = np.minimum(reach, settings["reach_px"])
    count = settings["slices"]
    slices, total = [], np.zeros(len(ys))
    for k in range(count):
        phi = (k + rot) / count * np.pi
        v, d, length, g = slice_frame(p, n, np.stack([np.cos(phi), np.sin(phi)], 1))
        total += length * (side_total(g) + side_total(-g))
        slices.append((phi, v, d, length, g))
    total = np.maximum(total, 1e-30)
    entries, reads = [], {"short": [], "coarse": [], "off": 0, "samples": 0}
    for phi, v, d, length, g in slices:
        for side in (1.0, -1.0):
            gs = side * g
            t_side = side_total(gs)
            share = length * t_side / BITS / total
            occupied = np.zeros(len(ys), np.uint32)
            steps = settings["short_steps"] + settings["long_steps"]
            for j in range(steps):
                short = j < settings["short_steps"]
                r, active = step_radius(j, settings, jitter, short_end, long_end)
                sx = xs + 0.5 + side * r * np.cos(phi)
                sy = ys + 0.5 + side * r * np.sin(phi)
                inside = active & (sx >= 0) & (sx < w) & (sy >= 0) & (sy < h)
                reads["off"] += int((active & ~inside).sum())
                reads["samples"] += int(active.sum())
                q, qb, src, valid, iy, ix, facing = sample(
                    frame, settings, short, sx, sy, thickness, cap
                )
                reads["short" if short else "coarse"].append(
                    (xs[inside] // TILE, iy[inside], ix[inside])
                )
                delta = q - p
                dist = np.linalg.norm(delta, axis=1)
                above = (delta * geo).sum(1) > ranges["plane"] * dist
                valid = inside & valid & (dist < near_range) & (dist > 0) & above
                a_front = side_angle(delta, v, d, side)
                a_back = side_angle(qb - p, v, d, side)
                u_front = side_share(a_front, gs, t_side)
                u_back = side_share(a_back, gs, t_side)
                mask = bit_range(
                    np.minimum(u_front, u_back), np.maximum(u_front, u_back)
                )
                mask = np.where(valid, mask, np.uint32(0))
                fresh = np.bitwise_count(mask & ~occupied)
                occupied |= mask
                if facing is not None and ranges["backface"]:
                    behind = (facing * delta).sum(1) >= 0
                    if ranges["backface"] == 1:
                        fresh = np.where(behind, 0, fresh)
                    else:
                        src = np.where(behind, -1 - src, src)
                got = np.nonzero(fresh)[0]
                if len(got):
                    weight = fresh[got] * share[got]
                    if facing is not None and ranges["facing"]:
                        cos = -(facing[got] * delta[got]).sum(1) / dist[got]
                        weight = weight * np.clip(cos, 0.0, 1.0)
                    level = np.full(len(got), 0 if short else 1, np.int8)
                    entries.append((pixel[got], src[got], weight, level))
    return entries, reads


def tile_reads(reads, level, y_tile, coarse_shape):
    """Per tile of the row (dict tile x -> count): the distinct pixels read outside the
    tile (short level) or the distinct coarse cells read (coarse level)."""
    if not reads:
        return {}
    tx = np.concatenate([r[0] for r in reads])
    iy = np.concatenate([r[1] for r in reads])
    ix = np.concatenate([r[2] for r in reads])
    if level == "short":
        outside = (iy // TILE != y_tile) | (ix // TILE != tx)
        tx, key = tx[outside], (iy * 100000 + ix)[outside]
    else:
        key = (iy >> coarse_shape) * 100000 + (ix >> coarse_shape)
    pairs = np.unique(tx.astype(np.int64) * (1 << 40) + key)
    tiles, counts = np.unique(pairs >> 40, return_counts=True)
    return dict(zip(tiles.tolist(), counts.tolist()))


def march(frame, receivers, ranges, settings=None, log=None):
    """The near operator of a frame: entries (pixel, source, weight, level) as arrays,
    the blocked share (H W,), and per tile the distinct reads of each level; `ranges`:
    near range, thickness, coarse cap (world), plane (the least rise over the surface),
    backface (0: a sample seen from behind brings the radiance the frame shows; 1: its
    bits are left to the far field; 2: it brings its indirect radiance alone, source
    -1 - pixel), facing (1: a full-resolution sample's bits count by its cosine toward
    the receiver)."""
    settings = {**SETTINGS, **(settings or {})}
    h, w = frame["depth"].shape
    parts, per_tile = [], {"short": [], "coarse": []}
    samples = off = 0
    for y0 in range(0, h, TILE):
        entries, reads = march_rows(frame, receivers, y0, ranges, settings)
        parts.extend(entries)
        samples, off = samples + reads["samples"], off + reads["off"]
        for level in ("short", "coarse"):
            counts = tile_reads(
                reads[level], level, y0 // TILE, settings["coarse_level"]
            )
            per_tile[level].extend(counts.get(t, 0) for t in range(-(-w // TILE)))
        if log:
            log(f"near: rows {y0 + TILE} of {h}")
    pixel, src, weight, level = (np.concatenate(c) for c in zip(*parts))
    blocked = np.bincount(pixel, weight, h * w)
    return {
        "pixel": pixel,
        "source": src,
        "weight": weight,
        "level": level,
        "blocked": blocked,
        "settings": settings,
        "samples": samples,
        "off_screen": off,
        "tile_short": np.array(per_tile["short"]),
        "tile_coarse": np.array(per_tile["coarse"]),
    }
