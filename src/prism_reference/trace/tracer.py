"""Ray tracing in numpy, float32: one ray with a stack, nearer child first; per pixel a
primary ray, its shadow, one diffuse bounce and its shadow."""

import numpy as np

from prism_reference.scene.frame import HEIGHT, WIDTH
from prism_reference.scene.generated import uniform
from prism_reference.trace.tree import LEAF, is_leaf

F = np.float32
TMAX = F(1e30)
STACK = 64
CHUNK = 1 << 16
SLAB_SCALE = F(1.0000004)
MIN_DIR = F(1e-12)
AMBIENT = F(0.1)
GI = F(0.5)
HORIZON = np.array([0.85, 0.88, 0.95], dtype=np.float32)
ZENITH = np.array([0.35, 0.55, 0.9], dtype=np.float32)
SEED = 7


def dot(a, b):
    """Row-wise dot product, summed left to right."""
    return (a[:, 0] * b[:, 0] + a[:, 1] * b[:, 1]) + a[:, 2] * b[:, 2]


def cross(a, b):
    """Row-wise cross product."""
    return np.stack(
        [
            a[:, 1] * b[:, 2] - a[:, 2] * b[:, 1],
            a[:, 2] * b[:, 0] - a[:, 0] * b[:, 2],
            a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0],
        ],
        axis=1,
    )


def camera_rays(camera, pixels):
    """Origins and directions (R, 3) of the primary rays of pixel numbers y * W + x."""
    x = (pixels % WIDTH).astype(np.float32) + F(0.5)
    y = (pixels // WIDTH).astype(np.float32) + F(0.5)
    sx = (x - camera[13]) / camera[12]
    sy = (y - camera[14]) / camera[12]
    right, up, fwd = camera[3:6], camera[6:9], camera[9:12]
    d = (fwd + right * sx[:, None]) - up * sy[:, None]
    return np.broadcast_to(camera[0:3], d.shape).copy(), d


def inverse_direction(d):
    """1 / d with components smaller than MIN_DIR replaced by +-MIN_DIR."""
    safe = np.where(np.abs(d) < MIN_DIR, np.copysign(MIN_DIR, d), d)
    return F(1.0) / safe


def box_test(box, ids, o, inv, best):
    """Hit flag and entry distance of boxes `ids` against rays (o, inv, best)."""
    b = box[ids]
    t0 = (b[:, :3] - o) * inv
    t1 = (b[:, 3:] - o) * inv
    near, far = np.minimum(t0, t1), np.maximum(t0, t1)
    entry = np.maximum(np.maximum(near[:, 0], near[:, 1]), np.maximum(near[:, 2], F(0)))
    exit_ = np.minimum(np.minimum(far[:, 0], far[:, 1]), far[:, 2]) * SLAB_SCALE
    return entry <= np.minimum(exit_, best), entry


def triangle_test(tris, leaf, o, d):
    """Hit flag, distance t and barycentrics u, v of triangles `leaf` against rays."""
    g = tris[leaf]
    v0, e1, e2 = g[:, 0:3], g[:, 3:6], g[:, 6:9]
    pv = cross(d, e2)
    det = dot(e1, pv)
    ok = det != 0
    inv = F(1.0) / np.where(ok, det, F(1.0))
    tv = o - v0
    u = dot(tv, pv) * inv
    ok &= (u >= 0) & (u <= 1)
    qv = cross(tv, e1)
    v = dot(d, qv) * inv
    ok &= (v >= 0) & (u + v <= 1)
    t = dot(e2, qv) * inv
    return ok & (t > 0), t, u, v


def trace(tree, o, d, tmax, any_hit=False):
    """Closest hit (or any hit) of rays (o, d) with t < tmax, in chunks of rays.

    Returns a dict: t, leaf (-1: none), u, v, nodes (box tests), leaves (triangles).
    """
    parts = [
        trace_chunk(tree, o[s : s + CHUNK], d[s : s + CHUNK], tmax, any_hit)
        for s in range(0, len(o), CHUNK)
    ]
    return {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}


def trace_chunk(tree, o, d, tmax, any_hit):
    """`trace` of one chunk of rays."""
    nodes, tris, leaf_tri = tree["nodes"], tree["tris"], tree["leaf_tri"]
    box = np.ascontiguousarray(nodes[:, :6]).view(np.float32)
    n = len(o)
    inv = inverse_direction(d)
    best = np.full(n, tmax, dtype=np.float32)
    out = {
        "t": best.copy(),
        "leaf": np.full(n, -1, dtype=np.int32),
        "u": np.zeros(n, dtype=np.float32),
        "v": np.zeros(n, dtype=np.float32),
        "nodes": np.ones(n, dtype=np.int32),
        "leaves": np.zeros(n, dtype=np.int32),
    }
    stack_node = np.zeros((n, STACK), dtype=np.int64)
    stack_t = np.zeros((n, STACK), dtype=np.float32)
    sp = np.zeros(n, dtype=np.int64)
    hit, entry = box_test(box, np.zeros(n, dtype=np.int64), o, inv, best)
    active = np.nonzero(hit)[0]
    stack_t[active, 0] = entry[active]
    sp[active] = 1
    while len(active):
        sp[active] -= 1
        top = sp[active]
        live = stack_t[active, top] <= best[active]
        node = stack_node[active, top][live]
        a = active[live]
        word = nodes[node, 6]
        leaf = is_leaf(word)
        r, idx = a[leaf], (word[leaf] & ~LEAF).astype(np.int64)
        if len(r):
            out["leaves"][r] += 1
            ok, t, u, v = triangle_test(tris, idx, o[r], d[r])
            better = ok & (t < best[r])
            if not any_hit:
                same = ok & (t == best[r]) & (out["leaf"][r] >= 0)
                old = leaf_tri[np.maximum(out["leaf"][r], 0)]
                better |= same & (leaf_tri[idx] < old)
            w = r[better]
            if not any_hit:
                best[w] = t[better]
            else:
                sp[w] = 0
            out["t"][w], out["leaf"][w] = t[better], idx[better]
            out["u"][w], out["v"][w] = u[better], v[better]
        i, nd = a[~leaf], node[~leaf]
        if len(i):
            c0, c1 = nodes[nd, 6].astype(np.int64), nodes[nd, 7].astype(np.int64)
            h0, t0 = box_test(box, c0, o[i], inv[i], best[i])
            h1, t1 = box_test(box, c1, o[i], inv[i], best[i])
            out["nodes"][i] += 2
            near1 = h1 & (~h0 | (t1 < t0))
            both = h0 & h1
            far_node = np.where(near1, c0, c1)
            far_t = np.where(near1, t0, t1)
            near_node = np.where(near1, c1, c0)
            near_t = np.where(near1, t1, t0)
            r = i[both]
            stack_node[r, sp[r]], stack_t[r, sp[r]] = far_node[both], far_t[both]
            sp[r] += 1
            r = i[h0 | h1]
            stack_node[r, sp[r]], stack_t[r, sp[r]] = (
                near_node[h0 | h1],
                near_t[h0 | h1],
            )
            sp[r] += 1
        active = active[sp[active] > 0]
    return out


def sky(d):
    """Sky colour of directions d: horizon to zenith by the height of the direction."""
    s = (d[:, 1] / np.sqrt(dot(d, d)))[:, None]
    s = np.minimum(np.maximum(s, F(0)), F(1))
    return HORIZON + (ZENITH - HORIZON) * s


def surface(scene, tree, hit, d):
    """Unit normal facing the ray and the interpolated colour at each hit."""
    g = tree["tris"][hit["leaf"]]
    n = cross(g[:, 3:6], g[:, 6:9])
    n = n / np.sqrt(dot(n, n))[:, None]
    n = np.where((dot(n, d) > 0)[:, None], -n, n)
    tri = tree["leaf_tri"][hit["leaf"]]
    c = scene["colors"][scene["indices"][tri]]
    u, v = hit["u"][:, None], hit["v"][:, None]
    return n, (c[:, 0] * ((F(1.0) - u) - v) + c[:, 1] * u) + c[:, 2] * v


def direct_light(scene, tree, p, n):
    """Ray origin above the surface and the diffuse term (0 where a shadow ray hits)."""
    o = p + n * scene["eps"][0]
    to_light = scene["light"] - o
    shadow = trace(tree, o, to_light, F(1.0), any_hit=True)["leaf"] >= 0
    cos = dot(n, to_light) * (F(1.0) / np.sqrt(dot(to_light, to_light)))
    return o, np.where(shadow, F(0), np.maximum(cos, F(0)))


def bounce_directions(pixels, n):
    """Unit directions along normal + a random unit vector, from the pixel hash."""
    g = np.empty((len(pixels), 3), dtype=np.float32)
    for k in range(3):
        r = [uniform(pixels, 4 * k + j, SEED) for j in range(4)]
        g[:, k] = (((r[0] + r[1]) + r[2]) + r[3]) - F(2.0)
    g2 = dot(g, g)
    g = np.where(
        (g2 < F(1e-12))[:, None], n, g / np.sqrt(np.maximum(g2, F(1e-12)))[:, None]
    )
    b = n + g
    b2 = dot(b, b)
    return np.where(
        (b2 < F(1e-6))[:, None], n, b / np.sqrt(np.maximum(b2, F(1e-6)))[:, None]
    )


def render_pixels(scene, tree, pixels):
    """Colour (R, 3) and the primary hits (a dict as from `trace`) of the pixels."""
    o, d = camera_rays(scene["camera"], pixels)
    hit = trace(tree, o, d, TMAX)
    colour = sky(d)
    h = np.nonzero(hit["leaf"] >= 0)[0]
    if len(h):
        sub = {k: v[h] for k, v in hit.items()}
        p = o[h] + d[h] * sub["t"][:, None]
        n, albedo = surface(scene, tree, sub, d[h])
        o2, direct = direct_light(scene, tree, p, n)
        db = bounce_directions(pixels[h], n)
        bounce = trace(tree, o2, db, TMAX)
        radiance = sky(db)
        b = np.nonzero(bounce["leaf"] >= 0)[0]
        if len(b):
            sub1 = {k: v[b] for k, v in bounce.items()}
            p1 = o2[b] + db[b] * sub1["t"][:, None]
            n1, albedo1 = surface(scene, tree, sub1, db[b])
            _, direct1 = direct_light(scene, tree, p1, n1)
            radiance[b] = albedo1 * (AMBIENT + direct1)[:, None]
        light = ((AMBIENT + direct)[:, None]) + GI * radiance
        colour[h] = albedo * light
    return colour, hit


def render(scene, tree, pixels=None):
    """Image (H, W, 3) and primary hit maps (t, tri, nodes, leaves) of all pixels.

    With `pixels` (pixel numbers y * W + x) the same values for those pixels, flat.
    """
    flat = pixels is None
    pix = np.arange(WIDTH * HEIGHT) if flat else np.asarray(pixels)
    colour, hit = render_pixels(scene, tree, pix)
    tri = np.where(hit["leaf"] >= 0, tree["leaf_tri"][np.maximum(hit["leaf"], 0)], -1)
    out = {
        "image": colour,
        "t": hit["t"],
        "tri": tri.astype(np.int32),
        "nodes": hit["nodes"],
        "leaves": hit["leaves"],
    }
    if flat:
        shapes = {"image": (HEIGHT, WIDTH, 3)}
        out = {k: v.reshape(shapes.get(k, (HEIGHT, WIDTH))) for k, v in out.items()}
    return out
