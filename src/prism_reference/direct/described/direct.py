"""The direct light of a described scene per pixel of its surface planes: one shadow
ray a punctual light, fixed points on each area light, fixed directions for the world;
out `diffuse_light`, `glossy_light` and `direct` in linear scene values, by light kind.
"""

import numpy as np

from prism_reference.direct.described.sample import (
    AREA_SAMPLES,
    WORLD_SAMPLES,
    area_points,
    cosine_directions,
    frames,
)
from prism_reference.direct.described.units import (
    ROUND,
    NotCarried,
    area_extent,
    area_radiance,
    light_axes,
    point_intensity,
    spot_attenuation,
    sun_irradiance,
    unit,
    world_light,
    world_radiance,
)
from prism_reference.material.brdf import d_ggx, diffuse, dot, f0, fresnel, v_smith
from prism_reference.trace.batch import trace
from prism_reference.trace.tracer import TMAX

KINDS = ("point", "spot", "sun", "area", "world")
KIND_OF = {"point": "point", "spot": "spot", "directional": "sun", "area": "area"}
RAY_OFFSET = 1e-5  # a shadow ray's start off the surface, by the scene's diagonal
LIGHT_END = 1e-4  # a ray to a point on a light stops this share of the way short
CHUNK = 1 << 15  # pixels lit at once
PLANES = ("diffuse_light", "glossy_light", "direct")


def described_lights(scene, folder):
    """The scene's lights prepared in radiometric units, its world (or None) and the
    list of what is not carried; folder: where the world's map lies."""
    lights, missing = [], []
    for node in scene.nodes:
        if node.light == -1:
            continue
        light = scene.lights[node.light]
        kind = KIND_OF.get(light.kind)
        if kind is None:
            missing.append(f"light kind {light.kind} ({node.name})")
            continue
        position, emits, _, _ = light_axes(node.world, light.kind)
        entry = {"kind": kind, "name": node.name}
        if kind in ("point", "spot"):
            entry |= {"position": position, "intensity": point_intensity(light)}
            if kind == "spot":
                entry |= {
                    "direction": emits,
                    "cones": (light.inner_cone, light.outer_cone),
                }
            if light.range is not None:
                missing.append(f"light range ({node.name})")
        elif kind == "sun":
            entry |= {"toward": -emits, "irradiance": sun_irradiance(light)}
        else:
            try:
                centre, u, v, normal, area = area_extent(light, node.world)
            except NotCarried as reason:
                missing.append(f"{reason} ({node.name})")
                continue
            entry |= {"centre": centre, "u": u, "v": v, "normal": normal, "area": area}
            entry |= {"radiance": area_radiance(light, area)}
            entry["points"] = area_points(light.shape in ROUND)
        lights.append(entry)
    try:
        world = world_light(scene.world, folder)
    except NotCarried as reason:
        missing.append(str(reason))
        world = None
    return lights, world, missing


def punctual_rays(light, p, origin, n):
    """Pixel rows, ray directions from the start points, tmax, unit l and weights w
    (L cos over the pdf, from the surface points p) of a point, spot or sun light."""
    rows = np.arange(len(origin))
    if light["kind"] == "sun":
        l = np.broadcast_to(light["toward"], origin.shape)
        w = light["irradiance"] * dot(n, l)[:, None]
        return rows, l, np.full(len(origin), TMAX), l, w
    d = light["position"] - p
    distance2 = np.maximum(dot(d, d), 1e-300)
    l = d / np.sqrt(distance2)[:, None]
    w = light["intensity"] * (dot(n, l) / distance2)[:, None]
    if light["kind"] == "spot":
        inner, outer = light["cones"]
        w = w * spot_attenuation(dot(-l, light["direction"]), inner, outer)[:, None]
    return rows, light["position"] - origin, np.ones(len(origin)), l, w


def area_rays(light, p, origin, n):
    """The same for an area light: AREA_SAMPLES fixed points on it, each weighted
    L cos cos' A / (AREA_SAMPLES d^2)."""
    s = light["points"]
    q = light["centre"] + s[:, :1] * light["u"] + s[:, 1:] * light["v"]
    d = (q[None, :, :] - p[:, None, :]).reshape(-1, 3)
    rows = np.repeat(np.arange(len(origin)), AREA_SAMPLES)
    distance2 = np.maximum(dot(d, d), 1e-300)
    l = d / np.sqrt(distance2)[:, None]
    facing = np.maximum(dot(-l, light["normal"]), 0.0)
    share = light["area"] / AREA_SAMPLES
    w = light["radiance"] * (dot(n[rows], l) * facing * share / distance2)[:, None]
    ray = (q[None, :, :] - origin[:, None, :]).reshape(-1, 3)
    return rows, ray, np.full(len(d), 1.0 - LIGHT_END), l, w


def world_rays(world, p, origin, n):
    """The same for the world: WORLD_SAMPLES cosine-weighted directions about n, each
    weighted pi L / WORLD_SAMPLES."""
    local = cosine_directions()
    t, b = frames(n)
    l = (
        local[None, :, :1] * t[:, None]
        + local[None, :, 1:2] * b[:, None]
        + local[None, :, 2:] * n[:, None]
    ).reshape(-1, 3)
    rows = np.repeat(np.arange(len(origin)), WORLD_SAMPLES)
    w = world_radiance(world, l) * (np.pi / WORLD_SAMPLES)
    return rows, l, np.full(len(l), TMAX), l, w


def shaded(rows, l, w, surface):
    """Per sample the diffuse light w / pi, the glossy light w D V F / f0 and the
    direct light w (diffuse (1 - F) + D V F), 0 where n.v <= 0 for the last two."""
    n, v = surface["n"][rows], surface["v"][rows]
    n_l, n_v = dot(n, l), dot(n, v)
    half = unit(v + l)
    a = surface["roughness"][rows] ** 2
    front = n_v > 0
    nl, nv = np.maximum(n_l, 1e-12), np.where(front, n_v, 1.0)
    colour = surface["f0"][rows]
    f = fresnel(colour, dot(v, half))
    specular = (d_ggx(dot(n, half), a) * v_smith(nl, nv, a))[:, None] * f
    glossy = np.where(colour > 0, specular / np.where(colour > 0, colour, 1.0), 0.0)
    lobe = surface["diffuse"][rows] * (1.0 - f) + specular
    keep = front[:, None]
    return w / np.pi, np.where(keep, w * glossy, 0.0), np.where(keep, w * lobe, 0.0)


def lit_chunk(lights, world, surface, p, origin, tree, sums, counts):
    """Adds each light's samples at one chunk of pixels into sums[kind]."""
    n = surface["n"]
    jobs = [(light["kind"], light) for light in lights]
    if world is not None:
        jobs.append(("world", world))
    for kind, light in jobs:
        if kind == "world":
            rows, d, tmax, l, w = world_rays(light, p, origin, n)
        elif kind == "area":
            rows, d, tmax, l, w = area_rays(light, p, origin, n)
        else:
            rows, d, tmax, l, w = punctual_rays(light, p, origin, n)
        live = np.any(w > 0, axis=1) & (dot(n[rows], l) > 0)
        rows, d, tmax, l, w = rows[live], d[live], tmax[live], l[live], w[live]
        if not len(rows):
            continue
        _, tri, _, _ = trace(tree, origin[rows], d, tmax, any_hit=True)
        counts["rays"] += len(rows)
        seen = tri < 0
        values = shaded(rows[seen], l[seen], w[seen], surface)
        for name, value in zip(PLANES, values, strict=True):
            for c in range(3):
                sums[kind][name][:, c] += np.bincount(
                    rows[seen], value[:, c], minlength=len(origin)
                )


def surface_of(planes, ys, xs, eye):
    """The chunk's shading inputs: normals turned toward the eye, view vector, the
    model's diffuse colour and f0, roughness; and the shadow rays' start points."""
    p = planes["position"][ys, xs].astype(np.float64)
    n = unit(planes["normal"][ys, xs])
    ng = unit(planes["geometric_normal"][ys, xs])
    v = unit(eye - p)
    sign = np.where(dot(ng, v) < 0, -1.0, 1.0)[:, None]
    base = planes["base_color"][ys, xs].astype(np.float64)
    metallic = planes["metallic"][ys, xs].astype(np.float64)
    surface = {
        "n": n * sign,
        "v": v,
        "roughness": planes["roughness"][ys, xs].astype(np.float64),
        "diffuse": diffuse(base, metallic),
        "f0": f0(base, metallic),
    }
    return surface, p, ng * sign


def direct_light(planes, eye, tree, diagonal, lights, world):
    """{plane: (H, W, 3) float32} for `PLANES` summed over the lights (`direct` with the
    emission), `kinds` {kind: those planes} and `rays` traced."""
    covered = planes["covered"]
    shape = covered.shape + (3,)
    kinds = sorted(
        {light["kind"] for light in lights} | ({"world"} if world else set())
    )
    kinds = [k for k in KINDS if k in kinds]
    out = {k: {name: np.zeros(shape, np.float32) for name in PLANES} for k in kinds}
    eps = RAY_OFFSET * diagonal
    ys, xs = np.nonzero(covered)
    counts = {"rays": 0}
    for start in range(0, len(ys), CHUNK):
        y, x = ys[start : start + CHUNK], xs[start : start + CHUNK]
        surface, p, ng = surface_of(planes, y, x, np.asarray(eye, np.float64))
        sums = {k: {name: np.zeros((len(y), 3)) for name in PLANES} for k in kinds}
        lit_chunk(lights, world, surface, p, p + ng * eps, tree, sums, counts)
        for k in kinds:
            for name in PLANES:
                out[k][name][y, x] = sums[k][name]
    total = {name: np.zeros(shape, np.float32) for name in PLANES}
    for k in kinds:
        for name in PLANES:
            total[name] += out[k][name]
    total["direct"] += np.where(covered[..., None], planes["emissive"], 0.0)
    return total | {"kinds": out, "rays": counts["rays"]}
