"""The near field's march: per pixel, slices of the screen in two levels (full resolution
within the tile's halo, the coarse copy beyond), each sample covering bits of the
cosine measure; the result is a sparse operator from the frame's radiance to the pixels.
"""

import numpy as np

from prism_reference.indirect.near.measure import (
    BITS,
    bit_range,
    side_share,
    side_share_free,
    side_total,
    slice_frame,
)
from prism_reference.indirect.near.pool import forked_map

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
    "tile": TILE,
    "angles": "exact",
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


def sample_previous(previous, settings, short, sx, sy, thickness, cap):
    """`sample` read from the previous frame at its screen (sx, sy): points and normal
    turned into the current camera's axes; sources index the previous frame."""
    q, qb, src, valid, iy, ix, facing = sample(
        previous["frame"], settings, short, sx, sy, thickness, cap
    )
    turn, offset = previous["rotation"], previous["offset"]
    q, qb = q @ turn.T + offset, qb @ turn.T + offset
    facing = None if facing is None else facing @ turn.T
    return q, qb, src, valid, iy, ix, facing


def previous_shift(previous, p):
    """Each receiver's offset (n, 2) from its screen position to its place in the
    previous frame, and whether it lies in front of the previous camera."""
    old = (p - previous["offset"]) @ previous["rotation"]
    f = previous["frame"]
    z = np.where(old[:, 2] > 0, old[:, 2], 1.0)
    u = f["cx"] + f["focal"] * old[:, 0] / z
    v = f["cy"] - f["focal"] * old[:, 1] / z
    return np.stack([u, v], 1), old[:, 2] > 0


def shares(delta, v, d, side, gs, t_side, settings):
    """A sample's share of the side's measure below its angle, by atan2 and the closed
    form (`exact`) or by `side_share_free`."""
    if settings["angles"] == "free":
        x, y = (delta * v).sum(1), side * (delta * d).sum(1)
        return side_share_free(x, y, gs, t_side)
    return side_share(side_angle(delta, v, d, side), gs, t_side)


def march_rows(frame, receivers, y0, ranges, settings):
    """The march of the receivers in rows [y0, y0 + tile): entries (pixel, source,
    weight, level) and the reads of each level; with frame["previous"], what lies
    outside a receiver's tile is read from the previous frame (levels 2 and 3)."""
    z = frame["depth"]
    h, w = z.shape
    tile = settings["tile"]
    previous = frame.get("previous")
    ys, xs = np.nonzero(receivers[y0 : y0 + tile])
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
    if previous is not None:
        old_at, seen = previous_shift(previous, p)
        shift = old_at - np.stack([xs + 0.5, ys + 0.5], 1)
        pw = previous["frame"]["depth"].shape[1]
        ph = previous["frame"]["depth"].shape[0]
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
                level = np.full(len(ys), 0 if short else 1, np.int8)
                if previous is not None:
                    own = short & (np.floor(sy) // tile == ys // tile)
                    own = own & (np.floor(sx) // tile == xs // tile)
                    ox, oy = sx + shift[:, 0], sy + shift[:, 1]
                    old = sample_previous(
                        previous, settings, short, ox, oy, thickness, cap
                    )
                    there = seen & (ox >= 0) & (ox < pw) & (oy >= 0) & (oy < ph)
                    inside = np.where(own, inside, active & there)
                    q, qb = np.where(own[:, None], q, old[0]), np.where(
                        own[:, None], qb, old[1]
                    )
                    src = np.where(own, src, old[2])
                    valid = np.where(own, valid, old[3])
                    iy, ix = np.where(own, iy, old[4]), np.where(own, ix, old[5])
                    if short:
                        facing = np.where(own[:, None], facing, old[6])
                    level = np.where(own, level, level + 2).astype(np.int8)
                reads["short" if short else "coarse"].append(
                    (xs[inside] // tile, iy[inside], ix[inside])
                )
                delta = q - p
                dist = np.linalg.norm(delta, axis=1)
                above = (delta * geo).sum(1) > ranges["plane"] * dist
                valid = inside & valid & (dist < near_range) & (dist > 0) & above
                u_front = shares(delta, v, d, side, gs, t_side, settings)
                u_back = shares(qb - p, v, d, side, gs, t_side, settings)
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
                    entries.append((pixel[got], src[got], weight, level[got]))
    return entries, reads


def tile_reads(reads, level, y_tile, coarse_shape, tile=TILE):
    """Per tile of the row (dict tile x -> count): the distinct pixels read outside the
    tile (short level) or the distinct coarse cells read (coarse level)."""
    if not reads:
        return {}
    tx = np.concatenate([r[0] for r in reads])
    iy = np.concatenate([r[1] for r in reads])
    ix = np.concatenate([r[2] for r in reads])
    if level == "short":
        outside = (iy // tile != y_tile) | (ix // tile != tx)
        tx, key = tx[outside], (iy * 100000 + ix)[outside]
    else:
        key = (iy >> coarse_shape) * 100000 + (ix >> coarse_shape)
    pairs = np.unique(tx.astype(np.int64) * (1 << 40) + key)
    tiles, counts = np.unique(pairs >> 40, return_counts=True)
    return dict(zip(tiles.tolist(), counts.tolist()))


def band(frame, receivers, ranges, settings, y0):
    """The band of tile rows from y0: its entries, samples, off-screen samples and per
    tile across the distinct reads of each level."""
    entries, reads = march_rows(frame, receivers, y0, ranges, settings)
    tile = settings["tile"]
    across = -(-frame["depth"].shape[1] // tile)
    counts = {}
    for level in ("short", "coarse"):
        got = tile_reads(
            reads[level], level, y0 // tile, settings["coarse_level"], tile
        )
        counts[level] = [got.get(t, 0) for t in range(across)]
    return entries, reads["samples"], reads["off"], counts


def march(frame, receivers, ranges, settings=None, log=None, workers=1):
    """The near operator of a frame: entries (pixel, source, weight, level: 0 short, 1
    coarse, + 2 read from frame["previous"] outside the receiver's tile) as arrays,
    the blocked share (H W,), and per tile the distinct reads of each level; `ranges`:
    near range, thickness, coarse cap (world), plane (the least rise over the surface),
    backface (0: a sample seen from behind brings the radiance the frame shows; 1: its
    bits are left to the far field; 2: it brings its indirect radiance alone, source
    -1 - pixel), facing (1: a full-resolution sample's bits count by its cosine toward
    the receiver). `workers` > 1: the bands of tile rows in forked processes."""
    settings = {**SETTINGS, **(settings or {})}
    h, w = frame["depth"].shape
    parts, per_tile = [], {"short": [], "coarse": []}
    samples = off = 0
    tile = settings["tile"]
    starts = range(0, h, tile)
    done = forked_map(band, (frame, receivers, ranges, settings), starts, workers)
    for y0, (entries, n, n_off, counts) in zip(starts, done):
        parts.extend(entries)
        samples, off = samples + n, off + n_off
        for level in ("short", "coarse"):
            per_tile[level].extend(counts[level])
        if log:
            log(f"near: rows {y0 + tile} of {h}")
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
