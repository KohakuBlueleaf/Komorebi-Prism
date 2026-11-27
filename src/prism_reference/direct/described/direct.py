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
from prism_reference.material.brdf import (
    DIELECTRIC_F0,
    d_charlie,
    d_ggx,
    diffuse,
    dot,
    lobe_albedo,
    multiple_scattering,
    sheen_scale,
    v_neubelt,
    v_smith,
    valid_normal,
)
from prism_reference.trace.batch import trace
from prism_reference.trace.tracer import TMAX

KINDS = ("point", "spot", "sun", "area", "world")
KIND_OF = {"point": "point", "spot": "spot", "directional": "sun", "area": "area"}
RAY_OFFSET = 1e-5  # a shadow ray's start off the surface, by the scene's diagonal
LIGHT_END = 1e-4  # a ray to a point on a light stops this share of the way short
CHUNK = 1 << 15  # pixels lit at once
PLANES = ("diffuse_light", "glossy_light", "specular", "sheen", "direct")


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
    """Per sample the diffuse light w / pi, the glossy light (the specular lobe's light
    over its directional albedo), the specular lobe's light w D V F M S, the sheen's
    w sheen D V and the direct light w ((diffuse (1 - F) + D V F M) S + sheen), S the
    sheen's albedo scaling. The specular lobe uses the valid normal (its cosine in place
    of the shading normal's in w), the others the shading normal; the specular and sheen
    lobes are 0 where their normal faces away from the eye, the diffuse is not."""
    n, v = surface["n"][rows], surface["v"][rows]
    n_l, n_v = dot(n, l), dot(n, v)
    half = unit(v + l)
    a = surface["roughness"][rows] ** 2
    front = n_v > 0
    nl, nv = np.maximum(n_l, 1e-12), np.where(front, n_v, 1.0)
    ns = surface["n_specular"][rows]
    ns_l, ns_v = dot(ns, l), dot(ns, v)
    turned = np.maximum(ns_l, 0.0) / nl
    nsl, nsv = np.maximum(ns_l, 1e-12), np.where(ns_v > 0, ns_v, 1.0)
    colour, f90 = surface["f0"][rows], surface["f90"][rows]
    schlick = (1.0 - np.clip(dot(v, half), 0.0, 1.0)) ** 5
    f = colour + (f90[:, None] - colour) * schlick[:, None]
    lobe = (d_ggx(dot(ns, half), a) * v_smith(nsl, nsv, a) * turned)[:, None] * f
    lobe = np.where((ns_v > 0)[:, None], lobe, 0.0)
    specular = lobe * surface["scattering"][rows]
    albedo = surface["albedo"][rows]
    glossy = np.where(albedo > 0, specular / np.where(albedo > 0, albedo, 1.0), 0.0)
    tint, sheen_rough = surface["sheen"][rows], surface["sheen_roughness"][rows]
    sheen = tint * (d_charlie(dot(n, half), sheen_rough) * v_neubelt(nl, nv))[:, None]
    under = sheen_scale(tint, nv, nl, sheen_rough)[:, None]
    keep = front[:, None]
    sheen = np.where(keep, sheen, 0.0)
    light = (surface["diffuse"][rows] * (1.0 - f) + specular) * under + sheen
    return (
        w / np.pi,
        w * glossy,
        w * specular * under,
        w * sheen,
        w * light,
    )


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


def zeros_or(planes, name, ys, xs, shape):
    """A plane's values at the pixels as float64, zeros when the planes lack it."""
    plane = planes.get(name)
    return np.zeros(shape) if plane is None else plane[ys, xs].astype(np.float64)


def surface_of(planes, ys, xs, eye):
    """The chunk's shading inputs (normals toward the eye, the specular's made valid for
    the view; the model's colours, roughness, the lobe's albedo and multiple-scattering
    factor) and the shadow rays' start points."""
    p = planes["position"][ys, xs].astype(np.float64)
    n = unit(planes["normal"][ys, xs])
    ng = unit(planes["geometric_normal"][ys, xs])
    v = unit(eye - p)
    sign = np.where(dot(ng, v) < 0, -1.0, 1.0)[:, None]
    n, ng = n * sign, ng * sign
    n_specular = valid_normal(n, ng, v)
    base = planes["base_color"][ys, xs].astype(np.float64)
    metallic = planes["metallic"][ys, xs].astype(np.float64)
    roughness = planes["roughness"][ys, xs].astype(np.float64)
    count = len(ys)
    dielectric = planes.get("specular_colour")
    dielectric = (
        np.full((count, 3), DIELECTRIC_F0)
        if dielectric is None
        else dielectric[ys, xs].astype(np.float64)
    )
    weight = planes.get("specular_weight")
    weight = np.ones(count) if weight is None else weight[ys, xs].astype(np.float64)
    m = metallic[:, None]
    f0 = dielectric * weight[:, None] * (1.0 - m) + base * m
    f90 = weight * (1.0 - metallic) + metallic
    n_v = np.clip(dot(n_specular, v), 0.0, 1.0)
    scattering = multiple_scattering(f0, n_v, roughness)
    surface = {
        "n": n,
        "n_specular": n_specular,
        "v": v,
        "roughness": roughness,
        "diffuse": diffuse(base, metallic),
        "f0": f0,
        "f90": f90,
        "scattering": scattering,
        "albedo": lobe_albedo(f0, f90, n_v, roughness) * scattering,
        "sheen": zeros_or(planes, "sheen_colour", ys, xs, (count, 3)),
        "sheen_roughness": zeros_or(planes, "sheen_roughness", ys, xs, (count,)),
    }
    return surface, p, ng


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
