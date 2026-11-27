"""Every option of the sun's shadow against the traced share on a scene's view: the
pixels a shadow texel spans, and per option the mean difference over the pixels facing
the sun and over the edge band, with its texel reads."""

import numpy as np

from prism_common.paths import data_root
from prism_reference.direct import shadow_cascade as cascade
from prism_reference.direct import shadow_filter as filters
from prism_reference.direct.frame import rasterize_lighted
from prism_reference.direct.lights import load, placeholder, shadow_side
from prism_reference.direct.shadow import shadow_map, sun_screen
from prism_reference.direct.shadow_traced import caster_tree, traced_sun
from prism_reference.material.kinds import EMISSIVE
from prism_reference.raster.setup import world_points
from prism_reference.scene.public.materials import load_materials
from prism_reference.scene.public.views import make_view

F = np.float32
ANGLE = 0.00918  # the sun's diameter in radians (Blender's sun default)
CHUNK = 1 << 16
OPTIONS = {
    "2x2": ("map", {"kind": "box", "width": 1}),
    "box3": ("map", {"kind": "box", "width": 3}),
    "box5": ("map", {"kind": "box", "width": 5}),
    "disk r2": ("map", {"kind": "disk", "radius": 2.0, "taps": 16}),
    "pcss": ("map", {"kind": "pcss", "angle": ANGLE, "taps": 16}),
    "side x2": ("double", {"kind": "box", "width": 1}),
    "cascade": ("cascade", {"kind": "box", "width": 1}),
    "cascade pcss": ("cascade", {"kind": "pcss", "angle": ANGLE, "taps": 16}),
}


def with_map(lights, view, materials, side):
    """The lights with the sun's map at `side`, the bias kept in texels."""
    distance = float(lights["shadow_texel"] * lights["shadow_camera"][12])
    texels = float(lights["shadow_bias"]) * distance**2 / float(lights["shadow_texel"])
    depth, cam, texel = shadow_map(view, lights["sun_direction"], materials, side)
    new = float(texel * cam[12])
    return lights | {
        "shadow_map": depth,
        "shadow_camera": cam,
        "shadow_texel": texel,
        "shadow_side": np.int32(side),
        "shadow_bias": F(texels * float(texel) / new**2),
    }


def facing_surface(view, materials, lights):
    """Points, normals and pixel centres of the covered pixels facing the sun, the
    frame's (H, W) and their (ys, xs)."""
    lit = rasterize_lighted(view, materials, lights, terms=("sun", "glass"))
    tri, depth = lit["tri"], lit["depth"]
    ys, xs = np.nonzero(tri >= 0)
    normals = lit["parts"]["normal"][ys, xs]
    kind = materials["kind"][np.maximum(lit["parts"]["material"][ys, xs], 0)]
    keep = (normals @ lights["sun_direction"] > 0) & (kind != EMISSIVE)
    ys, xs, normals = ys[keep], xs[keep], normals[keep]
    pixels = np.stack([xs + F(0.5), ys + F(0.5)], 1).astype(F)
    points = world_points(view["camera"], pixels[:, 0], pixels[:, 1], depth[ys, xs])
    return points, normals, pixels, tri.shape, (ys, xs), tri


def pixels_a_texel(smap, points, normals, rows, tri):
    """Median and 90th percentile of the pixels a shadow texel spans (linear)."""
    ys, xs = rows
    height, width = tri.shape
    right, down = np.minimum(xs + 1, width - 1), np.minimum(ys + 1, height - 1)
    same = (tri[ys, right] == tri[ys, xs]) & (tri[down, xs] == tri[ys, xs])
    same &= (right != xs) & (down != ys)
    order = np.full(tri.shape, -1, np.int64)
    order[ys, xs] = np.arange(len(ys))
    a, b = order[ys, right], order[down, xs]
    same &= (a >= 0) & (b >= 0)
    sx, sy, _ = sun_screen(smap["camera"], smap["texel"], points, normals)
    dx = np.stack([sx[a] - sx, sy[a] - sy], 1)[same]
    dy = np.stack([sx[b] - sx, sy[b] - sy], 1)[same]
    area = np.abs(dx[:, 0] * dy[:, 1] - dx[:, 1] * dy[:, 0])
    span = 1 / np.sqrt(area[area > 0])
    return {"median": float(np.median(span)), "p90": float(np.quantile(span, 0.9))}


def edge_band(share, rows, shape):
    """Pixels within two of a pixel whose share is strictly inside (0.02, 0.98) or
    whose 3 x 3 neighbourhood holds both sides of 0.5, as a mask over the rows."""
    image = np.full(shape, 0.5, F)
    image[rows] = share
    low, high = image < 0.5, image > 0.5
    edge = (image > 0.02) & (image < 0.98)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            edge |= np.roll(np.roll(low, dy, 0), dx, 1) & high
    for _ in range(2):
        edge = edge | np.roll(edge, 1, 0) | np.roll(edge, -1, 0)
        edge = edge | np.roll(edge, 1, 1) | np.roll(edge, -1, 1)
    return edge[rows]


def measure_view(name, rays):
    """{side, pixels a texel, per option its differences and reads} on view `name`."""
    data = data_root()
    view = make_view(name, data)
    materials, _ = load_materials(name, data)
    lights = load(name, data)
    side = shadow_side(lights)
    if placeholder(lights):
        lights = with_map(lights, view, materials, side)
    points, normals, pixels, shape, rows, tri = facing_surface(view, materials, lights)
    smap = filters.sun_map(lights)
    double = filters.sun_map(with_map(lights, view, materials, 2 * side))
    seen = (points - view["camera"][0:3]) @ view["camera"][9:12]
    reach = (float(max(seen.min(), view["camera"][15])), float(seen.max()))
    maps = cascade.cascade_maps(view, materials, lights, 2, side // 2, reach)
    tree, keep = caster_tree(view, materials)
    eps = float(view["eps"][0])
    sun = lights["sun_direction"]
    parts = []
    for i in range(0, len(points), CHUNK):
        part = slice(i, i + CHUNK)
        parts.append(
            traced_sun(
                tree,
                keep,
                materials,
                points[part],
                normals[part],
                sun,
                ANGLE,
                rays,
                eps,
                pixels[part],
            )
        )
    truth = np.concatenate(parts)
    shares = {}
    for key, (where, method) in OPTIONS.items():
        if where == "cascade":
            shares[key], _ = cascade.cascade_shadow(
                maps, points, normals, method, pixels
            )
        else:
            target = smap if where == "map" else double
            shares[key] = filters.filtered_shadow(
                target, points, normals, method, pixels
            )
    band = edge_band(truth, rows, shape) | edge_band(shares["2x2"], rows, shape)
    options = {}
    for key, share in shares.items():
        error = np.abs(share - truth)
        options[key] = {
            "band": round(float(error[band].mean()), 4),
            "facing": round(float(error.mean()), 4),
            "reads": filters.taps_of(OPTIONS[key][1]),
        }
    return {
        "view": name,
        "side": side,
        "facing pixels": len(points),
        "band pixels": int(band.sum()),
        "pixels a texel": pixels_a_texel(smap, points, normals, rows, tri),
        "cascade texels": [float(m["texel"]) for m in maps],
        "options": options,
    }
