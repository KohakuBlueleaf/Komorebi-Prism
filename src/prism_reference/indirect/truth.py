"""The gathered truth of the indirect light at a frame's pixels: paths of cosine rays
with the sky, the sun, the lamps and emission at their hits."""

import time

import numpy as np

from prism_reference.indirect.elements import (
    cosine_directions,
    triangle_colour,
    triangle_geometry,
)
from prism_reference.indirect.light import lamp_irradiance
from prism_reference.indirect.sky import sky_radiance
from prism_reference.material.kinds import EMISSIVE
from prism_reference.raster.setup import world_points
from prism_reference.raster.vector import dot3
from prism_reference.trace.batch import trace

F = np.float32
# Rays a pixel, the bounces of a path by default and the seed of its first segment (a
# segment's seed the one before it plus 1).
TRUTH_RAYS = 256
TRUTH_BOUNCES = 2
TRUTH_SEED = 21


def truth(
    scene,
    materials,
    lights,
    frame,
    tree,
    rays=TRUTH_RAYS,
    step=2,
    log=print,
    bounces=TRUTH_BOUNCES,
):
    """At the frame's visible non-emissive pixels (every `step`-th) `rays` cosine rays
    about the pixel's normal; per pixel the sky with visibility and each of `bounces`
    bounces of the sources (`bounce1` ... , `path`)."""
    cam, eps = scene["camera"], F(scene["eps"][0])
    tri = frame["tri"][::step, ::step]
    kind = materials["kind"][materials["material"]]
    iy, ix = np.nonzero((tri >= 0) & (kind[np.maximum(tri, 0)] != EMISSIVE))
    t = tri[iy, ix]
    px, py = (step * ix).astype(F) + F(0.5), (step * iy).astype(F) + F(0.5)
    position = world_points(cam, px, py, frame["depth"][::step, ::step][iy, ix])
    normal = frame["parts"]["normal"][::step, ::step][iy, ix].astype(F)
    _, _, flat = triangle_geometry(scene)
    g = flat[t].astype(F)
    g = np.where((dot3(g, cam[None, 0:3] - position) < 0)[:, None], -g, g)
    surfaces = {
        "flat": flat.astype(F),
        "colour": triangle_colour(materials),
        "kind": kind,
    }
    origin = position + g * eps
    pixel = (iy * (tri.shape[1]) + ix).astype(np.int64)
    names = ("sky", *(f"bounce{k}" for k in range(1, bounces + 1)))
    sums = {k: np.zeros((len(iy), 3)) for k in names}
    escape = np.zeros(len(iy))
    started = time.perf_counter()
    for k0 in range(0, rays, 4):
        ks = np.arange(k0, min(rays, k0 + 4))
        ii = np.repeat(np.arange(len(iy)), len(ks))
        index = np.repeat(pixel * rays, len(ks)) + np.tile(ks, len(iy))
        path(
            tree, lights, surfaces, origin[ii], normal[ii], index, eps, ii, sums, escape,
            bounces,
        )  # fmt: skip
        if k0 % 64 == 60:
            log(
                f"truth: {k0 + 4} of {rays} rays, {time.perf_counter() - started:.0f} s"
            )
    scale = np.pi / rays
    out = {k: v * scale for k, v in sums.items()}
    return (
        out
        | {"iy": iy, "ix": ix, "position": position, "normal": normal}
        | {"escape": escape / rays}
    )


def hit_direct(tree, lights, surfaces, origin, d, t, tri, eps):
    """At ray hits: the point, its normal facing the ray, the albedo (0 when emissive)
    and its outgoing light from the sources but the sky (sun with a shadow ray, lamps).
    """
    point = origin + d * t[:, None]
    n = surfaces["flat"][tri]
    n = np.where((dot3(n, d) > 0)[:, None], -n, n)
    glow = (surfaces["kind"][tri] == EMISSIVE)[:, None]
    colour = surfaces["colour"][tri]
    albedo = np.where(glow, F(0), colour)
    s = lights["sun_direction"].astype(F)
    cos = np.maximum(dot3(n, s[None, :]), F(0))
    lit = np.nonzero(cos > 0)[0]
    sun = np.zeros(len(point), F)
    if len(lit):
        o = point[lit] + n[lit] * eps
        _, block, _, _ = trace(tree, o, np.broadcast_to(s, o.shape), 1e30, any_hit=True)
        sun[lit] = cos[lit] * (block < 0)
    e = sun[:, None] * lights["sun_irradiance"] + lamp_irradiance(lights, point, n)
    out = np.where(
        glow, colour * F(lights["emissive_scale"]), albedo * F(1 / np.pi) * e
    )
    return point + n * eps, n, albedo, out


def path(
    tree, lights, surfaces, origin, normal, index, eps, owner, sums, escape, bounces
):
    """One path per ray, added to `sums` by `owner`: the sky where its first segment
    escapes; at its k-th hit (k up to `bounces`) the direct light there and the sky
    where the next segment escapes, both times the albedos before it (`bounce<k>`)."""
    d = cosine_directions(index, normal, TRUTH_SEED)
    t, tri, _, _ = trace(tree, origin, d, 1e30)
    out = tri < 0
    np.add.at(sums["sky"], owner[out], sky_radiance(lights, d[out]))
    escape += np.bincount(owner[out], minlength=len(escape))
    live = np.nonzero(~out)[0]  # the rays still on their path
    gain = np.ones((len(live), 1), F)
    o, t, tri = origin[live], t[live], tri[live]
    for k in range(1, bounces + 1):
        o, n, albedo, light = hit_direct(
            tree, lights, surfaces, o, d[live], t, tri, eps
        )
        np.add.at(sums[f"bounce{k}"], owner[live], gain * light)
        gain = gain * albedo
        d = np.zeros_like(d)
        d[live] = cosine_directions(index[live], n, TRUTH_SEED + k)
        last = k == bounces
        t, tri, _, _ = trace(tree, o, d[live], 1e30, any_hit=last)
        out = tri < 0
        sky = gain[out] * sky_radiance(lights, d[live][out])
        np.add.at(sums[f"bounce{k}"], owner[live[out]], sky)
        if last:
            break
        keep = ~out
        live, gain, o, t, tri = live[keep], gain[keep], o[keep], t[keep], tri[keep]
