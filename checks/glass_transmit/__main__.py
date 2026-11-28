"""The glass a DEPTH view lets light through (prism_reference.direct.transmit), no card:
on a written scene (a floor, two panes over it in part overlapping, one under it) seen
by the sun from above, tinted and grey, T against the panes' product texel for texel, its
kept form against the product's, the sun's share on the floor against the kept product
(and, T 1 everywhere, against sun_shadow bit for bit); on each
public scene of --scenes, T of the sun's map at sampled texels against the product along
each texel's ray through every glass triangle it meets nearer than the map's 1/z (exact
intersections; a texel within MARGIN of a glass triangle's edge, or whose glass lies
within TIE of the map's 1/z (glass on an opaque surface: float32 decides), left out;
both counted). One JSON
line; exit 1 on a texel apart. Example: python -m checks.glass_transmit --scenes
italian_flat_97f97a20ba"""

import argparse
import json
import sys

import numpy as np

from prism_common.paths import data_root
from prism_reference.direct.lights import load as load_lights
from prism_reference.direct.lights import shadow_side
from prism_reference.direct.shadow import FILL_SIDE, map_at, sun_camera, sun_shadow
from prism_reference.direct.transmit import (
    LOSS,
    kept,
    kept_at,
    map_kept,
    map_transmittance,
    page_side,
    pane_factors,
    sun_shares,
    t_channels,
)
from prism_reference.material.kinds import FLAT, TRANSPARENT
from prism_reference.raster.frames import layer_scene
from prism_reference.scene.public.materials import load_materials
from prism_reference.scene.public.table import table
from prism_reference.scene.public.views import make_view

F = np.float32
TOLERANCE = 1e-6  # T apart, relative
MARGIN = 1e-3  # a texel's ray this close (barycentric) to a glass edge is left out
TIE = 1e-5  # glass this close (relative 1/z) to the map's opaque 1/z is left out
TAU = np.array([[0.9, 0.7, 0.5], [0.5, 0.5, 0.5], [0.2, 0.2, 0.2]], dtype=F)
Z1 = 0.25  # the panes' far side (z): the floor beyond lies under no glass
GREY = np.array([0.7, 0.7, 0.7], dtype=F)  # pane A's tau in the grey scene


def quad(x0, x1, y, z1=1.0):
    """Two triangles of the rectangle x0..x1 by -1..z1 (z) at height y."""
    corners = np.array([[x0, y, -1], [x1, y, -1], [x1, y, z1], [x0, y, z1]], dtype=F)
    return corners, np.array([[0, 1, 2], [0, 2, 3]])


def written_scene(tau):
    """The floor (row 0, opaque), pane A at 1 over x < 0.25, pane B at 1.5 over x >
    -0.25 (both over z < Z1), pane C at -0.5 under the floor; their rows 1, 2, 3, their tau `tau`.
    """
    parts = [quad(-1, 1, 0), quad(-1, 0.25, 1, Z1), quad(-0.25, 1, 1.5, Z1)]
    parts.append(quad(-1, 1, -0.5))
    positions, indices, rows = [], [], []
    for row, (p, i) in enumerate(parts):
        indices.append(i + sum(len(q) for q in positions))
        positions.append(p)
        rows += [row, row]
    scene = {"positions": np.concatenate(positions), "indices": np.concatenate(indices)}
    materials = {
        "kind": np.array([FLAT, TRANSPARENT, TRANSPARENT, TRANSPARENT]),
        "material": np.array(rows),
        "transmission": np.concatenate([np.ones((1, 3), dtype=F), tau]),
    }
    return scene, materials


def grown(mask):
    """`mask` with every neighbour (3 x 3) of a set element set."""
    padded = np.pad(mask, 1)
    out = np.zeros_like(mask)
    for dy in range(3):
        for dx in range(3):
            out |= padded[dy : dy + mask.shape[0], dx : dx + mask.shape[1]]
    return out


def written_report(tau, channels):
    """T of the written scene with panes `tau` against the panes' product, full and
    kept (its channels resolved to `channels`), the sun's share on the floor against the
    kept product, and against sun_shadow with T 1."""
    scene, materials = written_scene(tau)
    clear = materials["kind"][materials["material"]] == TRANSPARENT
    sun = np.array([0.0, 1.0, 0.0], dtype=F)
    camera = sun_camera(scene["positions"], sun, FILL_SIDE)
    depth = map_at(layer_scene(scene, ~clear), camera, None, FILL_SIDE)
    through = map_transmittance(scene, camera, materials, depth)
    side = FILL_SIDE
    s = np.arange(side, dtype=np.float64) + 0.5
    focal, cx, cy = (float(camera[k]) for k in (12, 13, 14))
    eye_height = float(camera[1])
    # texel centres on the floor (y 0): x along `right`, z along `up` (sun from +y)
    right, up = camera[3:6].astype(np.float64), camera[6:9].astype(np.float64)
    xs = (s - cx) / focal * eye_height
    ys = -(s - cy) / focal * eye_height
    world = xs[None, :, None] * right + ys[:, None, None] * up
    wx, wz = world[..., 0], world[..., 2]
    on_floor = (np.abs(wx) < 1) & (np.abs(wz) < 1)
    want = np.ones((side, side, 3))
    for x0, x1, row in ((-1, 0.25, 0), (-0.25, 1, 1)):
        # each pane's own projection: its height scales its footprint
        height = (1.0, 1.5)[row]
        px, pz = (
            wx * (eye_height - height) / eye_height,
            wz * (eye_height - height) / eye_height,
        )
        cover = (px > x0) & (px < x1) & (pz > -1) & (pz < Z1)
        want = np.where(cover[..., None], want * tau[row] * float(LOSS), want)
    edge = np.zeros((side, side), dtype=bool)
    for x0, x1, height in ((-1, 0.25, 1.0), (-0.25, 1, 1.5), (-1, 1, 0.0)):
        k = (eye_height - height) / eye_height
        texel = eye_height / focal
        for bound in (x0 * 1.0, x1 * 1.0):
            edge |= np.abs(wx * k - bound) < 2 * texel
        edge |= np.abs(np.abs(wz * k) - 1) < 2 * texel
        edge |= np.abs(wz * k - Z1) < 2 * texel
    judged = on_floor & ~edge
    apart = np.abs(through - want) > TOLERANCE * np.maximum(want, 1e-12)
    form = map_kept(scene, camera, materials, depth)
    wanted = kept(want, channels)
    k = form["scale"]
    block_edge = (~judged).reshape(side // k, k, side // k, k).any(axis=(1, 3))
    block_edge = grown(block_edge)
    codes_apart = np.abs(form["codes"].astype(int) - wanted["codes"]).max(axis=2) > 1
    out = {
        "channels": form["channels"],
        "channels_apart": int(form["channels"] != channels),
        "texels_judged": int(judged.sum()),
        "texels_apart": int((apart.any(axis=2) & judged).sum()),
        "texels_crossing": int(((want < 1).any(axis=2) & judged).sum()),
        "kept_judged": int((~block_edge).sum()),
        "kept_apart": int((codes_apart & ~block_edge).sum()),
        "pages_present": int(form["present"].sum()),
        "pages": int(form["present"].size),
        "absent_not_one": int(
            (form["codes"] != 255)
            .any(axis=2)[
                np.repeat(
                    np.repeat(~form["present"], page_side(channels), 0),
                    page_side(channels),
                    1,
                )[: side // k, : side // k]
            ]
            .sum()
        ),
    }
    rng = np.random.default_rng(1)
    points = np.stack(
        [rng.uniform(-0.9, 0.9, 4096), np.zeros(4096), rng.uniform(-0.9, 0.9, 4096)], 1
    ).astype(F)
    normals = np.tile(np.array([0, 1, 0], dtype=F), (len(points), 1))
    lights = {
        "shadow_map": depth,
        "shadow_camera": camera,
        "shadow_texel": F(eye_height / focal),
        "shadow_bias": F(0),
        "shadow_transmit": form,
    }
    shares = sun_shares(lights, points, normals)
    px = ((points.astype(np.float64) @ right) / eye_height * focal + cx).astype(int)
    py = (cy - (points.astype(np.float64) @ up) / eye_height * focal).astype(int)
    inside = (px >= 1) & (px < side - 1) & (py >= 1) & (py < side - 1)
    cy, cx = np.clip(py, 0, side - 1), np.clip(px, 0, side - 1)
    steady = inside & ~block_edge[cy // k, cx // k]
    expected = kept_at(wanted, py[steady], px[steady])
    out["share_points"] = int(steady.sum())
    out["share_apart"] = int(
        (np.abs(shares[steady] - expected) > 1.5 / 255).any(axis=1).sum()
    )
    plain = lights | {"shadow_transmit": kept(np.ones_like(through), channels)}
    one = sun_shares(plain, points, normals)
    alone = sun_shadow(plain, points, normals)
    out["one_apart_from_sun_shadow"] = int((one != alone[:, None]).any(axis=1).sum())
    return out


def rays_through(camera, sx, sy):
    """Origins (n, 3) and unit-depth directions (n, 3) (their forward part 1) of the
    rays of a camera through map coordinates sx, sy."""
    c = camera.astype(np.float64)
    eye, right, up, forward, focal = c[0:3], c[3:6], c[6:9], c[9:12], c[12]
    d = forward[None] + ((sx - c[13]) / focal)[:, None] * right
    d = d - ((sy - c[14]) / focal)[:, None] * up
    return np.broadcast_to(eye, d.shape), d


def traced_product(scene, materials, camera, sx, sy, opaque):
    """The product of tau LOSS along each ray through every glass triangle met nearer
    than `opaque` (1/z), whether a hit lies within MARGIN of a triangle's edge and
    whether one lies within TIE of `opaque`."""
    clear = np.nonzero(materials["kind"][materials["material"]] == TRANSPARENT)[0]
    tri = scene["positions"][scene["indices"][clear]].astype(np.float64)
    factors = pane_factors(materials, clear).astype(np.float64)
    origin, direction = rays_through(camera, sx, sy)
    product = np.ones((len(sx), 3))
    near_edge = np.zeros(len(sx), dtype=bool)
    tie = np.zeros(len(sx), dtype=bool)
    for s in range(0, len(tri), 256):
        t3 = tri[s : s + 256]
        e1, e2 = t3[:, 1] - t3[:, 0], t3[:, 2] - t3[:, 0]
        p = np.cross(direction[:, None], e2[None])
        det = np.einsum("tk,ntk->nt", e1, p)
        ok = np.abs(det) > 1e-18
        inv = 1 / np.where(ok, det, 1)
        tv = origin[:, None] - t3[None, :, 0]
        u = np.einsum("ntk,ntk->nt", tv, p) * inv
        q = np.cross(tv, e1[None])
        v = np.einsum("ntk,nk->nt", q, direction) * inv
        t = np.einsum("ntk,tk->nt", q, e2) * inv
        w = 1 - u - v
        hit = ok & (u >= 0) & (v >= 0) & (w >= 0) & (t > 0)
        inverse = 1 / np.where(t > 0, t, 1)
        nearer = hit & (inverse > opaque[:, None])
        tie |= (hit & (np.abs(inverse - opaque[:, None]) <= TIE * opaque[:, None])).any(
            1
        )
        product *= np.where(nearer[..., None], factors[s : s + 256][None], 1).prod(1)
        close = ok & (t > 0) & (np.minimum(np.minimum(u, v), w) > -MARGIN)
        close &= np.minimum(np.minimum(np.abs(u), np.abs(v)), np.abs(w)) < MARGIN
        near_edge |= close.any(axis=1)
    return product, near_edge, tie


def public_report(name, samples, rng):
    """T of the sun's map of a public scene at sampled texels against traced products."""
    lights = load_lights(name, data_root())
    materials = load_materials(name, data_root())[0]
    scene = make_view(f"{name}_{next(iter(table()[name]['views']))}", data_root())
    side = shadow_side(lights)
    camera = sun_camera(scene["positions"], lights["sun_direction"], side)
    clear = materials["kind"][materials["material"]] == TRANSPARENT
    if not clear.any():
        return {"glass_triangles": 0}
    depth = map_at(scene, camera, materials, side)
    through = map_transmittance(scene, camera, materials, depth)
    iy, ix = rng.integers(0, side, samples), rng.integers(0, side, samples)
    want, near_edge, tie = traced_product(
        scene, materials, camera, ix + 0.5, iy + 0.5, depth[iy, ix].astype(np.float64)
    )
    got = through[iy, ix].astype(np.float64)
    judged = ~near_edge & ~tie
    apart = (np.abs(got - want) > 1e-5 * np.maximum(want, 1e-12)).any(axis=1) & judged
    form = kept(through, t_channels(materials, np.arange(len(scene["indices"]))))
    return {
        "glass_triangles": int(clear.sum()),
        "channels": form["channels"],
        "pages_present": int(form["present"].sum()),
        "pages": int(form["present"].size),
        "texels_judged": int(judged.sum()),
        "texels_at_an_edge": int(near_edge.sum()),
        "texels_tied": int(tie.sum()),
        "texels_crossing": int(((want < 1).any(axis=1) & judged).sum()),
        "texels_apart": int(apart.sum()),
    }


def parse():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--scenes", nargs="*", default=[])
    parser.add_argument("--samples", type=int, default=20_000)
    parser.add_argument("--seed", type=int, default=1)
    return parser.parse_args()


def main():
    args = parse()
    rng = np.random.default_rng(args.seed)
    record = {
        "written_tinted": written_report(TAU, 3),
        "written_grey": written_report(np.concatenate([GREY[None], TAU[1:]]), 1),
    }
    for name in args.scenes:
        record[name] = public_report(name, args.samples, rng)
    keys = ("texels_apart", "share_apart", "one_apart_from_sun_shadow")
    keys += ("channels_apart", "kept_apart", "absent_not_one")
    apart = sum(r.get(key, 0) for r in record.values() for key in keys)
    print(json.dumps({"ok": apart == 0, **record}))
    return 0 if apart == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
