"""Filters of the sun's shadow map beside the 2 x 2 one: a wider box, rotated disk taps
and the penumbra from a blocker search (PCSS), over one map or a cascade's map."""

import numpy as np

from prism_reference.direct.shadow import sun_screen

F = np.float32
# The disk's taps by the golden angle and the interleaved gradient noise's numbers.
GOLDEN = F(np.pi * (3.0 - np.sqrt(5.0)))
NOISE = (F(52.9829189), F(0.06711056), F(0.00583715))
# The receiver plane's steepest slope, in texel widths of distance a texel.
STEEPEST = F(10)


def sun_map(lights):
    """The lights' map as a filter reads it: 1/z, camera, texel's world size, bias."""
    return {
        "depth": lights["shadow_map"],
        "camera": lights["shadow_camera"],
        "texel": lights["shadow_texel"],
        "bias": lights["shadow_bias"],
    }


def lit_at(smap, w, ix, iy):
    """1 where the texels (ix, iy) do not hide 1/z w (outside the map: lit), else 0."""
    depth = smap["depth"]
    side = depth.shape[0]
    inside = (ix >= 0) & (ix < side) & (iy >= 0) & (iy < side)
    stored = depth[np.clip(iy, 0, side - 1), np.clip(ix, 0, side - 1)]
    return np.where(inside & (w < stored - smap["bias"]), F(0), F(1))


def receiver_plane(smap, normals, w):
    """The receiver's distance change (gx, gy) a texel along the map's x and y, from
    its normals (n, 3) in the map's camera, at most STEEPEST texel widths."""
    cam = smap["camera"]
    nr, nu, nf = normals @ cam[3:6], normals @ cam[6:9], normals @ cam[9:12]
    across = (F(1) / w) / cam[12]
    facing = np.where(np.abs(nf) > F(1e-6), nf, F(-1e-6))
    limit = STEEPEST * across
    gx = np.clip(-nr / facing * across, -limit, limit)
    gy = np.clip(nu / facing * across, -limit, limit)
    return gx, gy


def shifted(w, plane, ox, oy):
    """The receiver's 1/z (n,) at offsets (ox, oy) texels on its plane (None: w)."""
    if plane is None:
        return w
    return F(1) / (F(1) / w + plane[0] * ox + plane[1] * oy)


def box_pcf(smap, sx, sy, w, width=1, plane=None):
    """The mean of width x width (odd) bilinear 2 x 2 filters one texel apart about
    (sx, sy): (width + 1)^2 texel reads, width 1 without a plane the present filter;
    plane: the receiver's (`receiver_plane`)."""
    if width < 1 or width % 2 == 0:
        raise ValueError(f"a box filter's width is odd and 1 or more, not {width}")
    gx, gy = sx - F(0.5), sy - F(0.5)
    x0, y0 = np.floor(gx), np.floor(gy)
    fx, fy = gx - x0, gy - y0
    half = (width - 1) // 2
    x0 = x0.astype(np.int64) - half
    y0 = y0.astype(np.int64) - half

    def weights(f):
        ones = [np.ones_like(f)] * (width - 1)
        return [F(1) - f, *ones, f]

    wx, wy = weights(fx), weights(fy)
    total = np.zeros_like(sx)
    for j in range(width + 1):
        row = np.zeros_like(sx)
        for i in range(width + 1):
            ix, iy = x0 + i, y0 + j
            at = shifted(w, plane, ix + F(0.5) - sx, iy + F(0.5) - sy)
            row = row + lit_at(smap, at, ix, iy) * wx[i]
        total = total + row * wy[j]
    return total / F(width * width)


def bilinear(smap, sx, sy, w):
    """The 2 x 2 filter at (sx, sy) of 1/z w: four texel reads."""
    return box_pcf(smap, sx, sy, w, 1)


def pixel_turn(px, py):
    """A turn in [0, 2 pi) per pixel centre (px, py): interleaved gradient noise."""
    a, b, c = NOISE
    inner = b * px + c * py
    value = a * (inner - np.floor(inner))
    return F(2 * np.pi) * (value - np.floor(value))


def disk_offsets(taps, turn):
    """Offsets (n, taps, 2) in the unit disk: golden-angle spiral turned by turn (n,)."""
    k = np.arange(taps, dtype=np.float32)
    radius = np.sqrt((k + F(0.5)) / F(taps))
    angle = k * GOLDEN + turn[:, None]
    return np.stack([radius * np.cos(angle), radius * np.sin(angle)], -1)


def disk_pcf(smap, sx, sy, w, radius, taps, turn, plane=None):
    """The mean of `taps` bilinear filters at the disk of `radius` texels (n,) about
    (sx, sy), turned by `turn` (n,), each at the receiver's plane: 4 taps reads."""
    offsets = disk_offsets(taps, turn) * radius[:, None, None]
    total = np.zeros_like(sx)
    for t in range(taps):
        ox, oy = offsets[:, t, 0], offsets[:, t, 1]
        at = shifted(w, plane, ox, oy)
        total = total + bilinear(smap, sx + ox, sy + oy, at)
    return total / F(taps)


def pcss(smap, sx, sy, w, angle, taps, turn, plane=None, search_taps=None):
    """Sun share from a blocker search over the disk the sun of `angle` (radians, its
    diameter) spans from the camera's near distance, then a disk filter of the
    penumbra's half width; search_taps + 4 taps texel reads. Returns share, radius."""
    search_taps = search_taps or taps
    focal = smap["camera"][12]
    receiver = F(1) / w
    spread = F(np.tan(angle / 2))
    reach = np.maximum((receiver - smap["camera"][15]) * spread * focal / receiver, 1)
    offsets = disk_offsets(search_taps, turn) * reach[:, None, None]
    depth = smap["depth"]
    side = depth.shape[0]
    found = np.zeros_like(sx)
    nearer = np.zeros_like(sx)
    for t in range(search_taps):
        ix = np.floor(sx + offsets[:, t, 0]).astype(np.int64)
        iy = np.floor(sy + offsets[:, t, 1]).astype(np.int64)
        inside = (ix >= 0) & (ix < side) & (iy >= 0) & (iy < side)
        stored = depth[np.clip(iy, 0, side - 1), np.clip(ix, 0, side - 1)]
        at = shifted(w, plane, offsets[:, t, 0], offsets[:, t, 1])
        block = inside & (at < stored - smap["bias"])
        found = found + block
        gap = F(1) / at - F(1) / np.maximum(stored, F(1e-30))
        nearer = nearer + np.where(block, gap, F(0))
    half = nearer / np.maximum(found, F(1)) * spread * focal / receiver
    radius = np.where(found > 0, np.maximum(half, F(0)), F(0))
    share = disk_pcf(smap, sx, sy, w, radius, taps, turn, plane)
    return np.where(found > 0, share, F(1)), radius


def filtered_shadow(smap, points, normals, method, pixels=None):
    """Sun share (n,) at points (n, 3), normals (n, 3) through one map by `method`:
    {"kind": "box", "width"} | {"kind": "disk", "radius", "taps"} | {"kind": "pcss",
    "angle", "taps"}; pixels (n, 2) the pixel centres the disk's turn hashes. All but
    the 2 x 2 filter compare each tap at the receiver's plane."""
    sx, sy, w = sun_screen(smap["camera"], smap["texel"], points, normals)
    plane = receiver_plane(smap, normals, w)
    turn = np.zeros(len(points), dtype=np.float32)
    if pixels is not None:
        turn = pixel_turn(pixels[:, 0], pixels[:, 1])
    match method["kind"]:
        case "box":
            width = method.get("width", 1)
            return box_pcf(smap, sx, sy, w, width, None if width == 1 else plane)
        case "disk":
            radius = np.full(len(points), F(method["radius"]))
            return disk_pcf(smap, sx, sy, w, radius, method["taps"], turn, plane)
        case "pcss":
            angle, taps = method["angle"], method["taps"]
            share, _ = pcss(smap, sx, sy, w, angle, taps, turn, plane)
            return share
    raise ValueError(f"unknown shadow filter {method['kind']!r}")


def taps_of(method):
    """Texel reads a pixel makes by `method` (as filtered_shadow)."""
    match method["kind"]:
        case "box":
            return (method.get("width", 1) + 1) ** 2
        case "disk":
            return 4 * method["taps"]
        case "pcss":
            return method.get("search_taps", method["taps"]) + 4 * method["taps"]
    raise ValueError(f"unknown shadow filter {method['kind']!r}")
