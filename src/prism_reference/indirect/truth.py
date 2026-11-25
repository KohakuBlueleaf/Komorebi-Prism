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
# Rays a pixel and the seeds of the three path segments.
TRUTH_RAYS = 256
TRUTH_SEEDS = (21, 22, 23)


def truth(scene, materials, lights, frame, tree, rays=TRUTH_RAYS, step=2, log=print):
    """At the frame's visible non-emissive pixels (every `step`-th) `rays` cosine rays
    about the pixel's normal; per pixel the sky with visibility and one and two bounces
    of the sources (`path`)."""
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
    sums = {k: np.zeros((len(iy), 3)) for k in ("sky", "bounce1", "bounce2")}
    escape = np.zeros(len(iy))
    started = time.perf_counter()
    for k0 in range(0, rays, 4):
        ks = np.arange(k0, min(rays, k0 + 4))
        ii = np.repeat(np.arange(len(iy)), len(ks))
        index = np.repeat(pixel * rays, len(ks)) + np.tile(ks, len(iy))
        path(
            tree, lights, surfaces, origin[ii], normal[ii], index, eps, ii, sums, escape
        )
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


def path(tree, lights, surfaces, origin, normal, index, eps, owner, sums, escape):
    """One path per ray, added to `sums` by `owner`: the sky where it escapes; at its
    first hit the direct light and one more cosine ray (`bounce1`), then one more hit
    and ray (`bounce2`)."""
    seed1, seed2, seed3 = TRUTH_SEEDS
    d = cosine_directions(index, normal, seed1)
    t, tri, _, _ = trace(tree, origin, d, 1e30)
    out = tri < 0
    np.add.at(sums["sky"], owner[out], sky_radiance(lights, d[out]))
    escape += np.bincount(owner[out], minlength=len(escape))
    h = np.nonzero(~out)[0]
    o1, n1, a1, l1 = hit_direct(
        tree, lights, surfaces, origin[h], d[h], t[h], tri[h], eps
    )
    np.add.at(sums["bounce1"], owner[h], l1)
    d2 = cosine_directions(index[h], n1, seed2)
    t2, tri2, _, _ = trace(tree, o1, d2, 1e30)
    out2 = tri2 < 0
    np.add.at(
        sums["bounce1"], owner[h[out2]], a1[out2] * sky_radiance(lights, d2[out2])
    )
    g = np.nonzero(~out2)[0]
    hit2 = hit_direct(tree, lights, surfaces, o1[g], d2[g], t2[g], tri2[g], eps)
    o2, n2, a2, l2 = hit2
    np.add.at(sums["bounce2"], owner[h[g]], a1[g] * l2)
    d3 = cosine_directions(index[h[g]], n2, seed3)
    _, tri3, _, _ = trace(tree, o2, d3, 1e30, any_hit=True)
    out3 = np.nonzero(tri3 < 0)[0]
    gain = a1[g[out3]] * a2[out3]
    np.add.at(sums["bounce2"], owner[h[g[out3]]], gain * sky_radiance(lights, d3[out3]))
