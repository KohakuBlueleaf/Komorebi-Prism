"""The light a DEPTH view lets through its glass: beside a map's nearest opaque 1/z, the
product T (H, W, 3) of every glass fragment nearer than it, each its material's
transmission tau times the two faces' loss at normal incidence; the sun's T and the
share a point gets through it; T as kept (8 bits, a scale of the map, grey or RGB by
the scene's glass, pages of all 1 absent)."""

import numpy as np

from prism_reference.direct.glass import GLASS_F0
from prism_reference.direct.shadow import FILL_SIDE, quadrant_camera, sun_screen
from prism_reference.material.kinds import TRANSPARENT
from prism_reference.raster.fill import CHUNK, bin_triangles
from prism_reference.raster.frames import layer_scene
from prism_reference.raster.setup import grid, setup
from prism_reference.scene.frame import TILE

F = np.float32
LOSS = F((1 - GLASS_F0) * (1 - GLASS_F0))  # a pane's two faces at normal incidence
T_SCALE = 2  # map texels a kept T texel spans, each way: half resolution
PAGE_BYTES = 4096
WORD_BYTES = {1: 1, 3: 4}  # a texel's bytes, grey and RGB (the fourth byte unused)


def pane_factors(materials, triangles):
    """tau LOSS (n, 3) of each of `triangles`' materials."""
    return materials["transmission"][materials["material"][triangles]] * LOSS


def tile_product(records, members, factors, opaque, tx, ty):
    """T (32, 32, 3) and the fragments counted (32, 32) of one tile: the product of
    `factors` of each member covering a pixel (FILL's rule) whose drawn 1/z (held as
    FILL holds it) is nearer than `opaque`."""
    px = (F(tx * TILE) + np.arange(TILE, dtype=F) + F(0.5))[None, None, :]
    py = (F(ty * TILE) + np.arange(TILE, dtype=F) + F(0.5))[None, :, None]
    cols = (np.arange(TILE) + tx * TILE)[None, None, :]
    rows = (np.arange(TILE) + ty * TILE)[None, :, None]
    product = np.ones((TILE, TILE, 3), dtype=F)
    count = np.zeros((TILE, TILE), dtype=np.int32)
    for s in range(0, len(members), CHUNK):
        m = members[s : s + CHUNK]
        a, b, c = (records[k][m][:, :, None, None] for k in ("a", "b", "c"))
        tl = records["top_left"][m][:, :, None, None]
        e = (a * px[:, None] + b * py[:, None]) + c
        inside = ((e > 0) | ((e == 0) & tl)).all(axis=1)
        box = records["box"][m]
        inside &= (cols >= box[:, 0, None, None]) & (cols <= box[:, 1, None, None])
        inside &= (rows >= box[:, 2, None, None]) & (rows <= box[:, 3, None, None])
        wp, held = records["w_planes"][m], records["w_range"][m]
        w = (wp[:, 0, None, None] * px + wp[:, 1, None, None] * py) + wp[
            :, 2, None, None
        ]
        w = np.minimum(np.maximum(w, held[:, 0, None, None]), held[:, 1, None, None])
        nearer = inside & (w > opaque[None])
        product *= np.where(nearer[..., None], factors[m][:, None, None, :], F(1)).prod(
            0
        )
        count += nearer.sum(axis=0).astype(np.int32)
    return product, count


def transmittance(view, materials, opaque):
    """T (H, W, 3) float32 of a view whose nearest opaque 1/z is `opaque` (H, W) (0:
    none), 1 where no glass is nearer, and the glass fragments counted (H, W)."""
    out = np.ones(opaque.shape + (3,), dtype=F)
    count = np.zeros(opaque.shape, dtype=np.int32)
    clear = materials["kind"][materials["material"]] == TRANSPARENT
    if not clear.any():
        return out, count
    records = setup(layer_scene(view, clear))
    if len(records["tri"]) == 0:
        return out, count
    across, down = grid(view)
    _, offsets, members = bin_triangles(records, across, down)
    factors = pane_factors(materials, records["tri"])
    for t in range(across * down):
        tile = members[offsets[t] : offsets[t + 1]]
        if len(tile) == 0:
            continue
        ty, tx = divmod(t, across)
        ys, xs = slice(ty * TILE, (ty + 1) * TILE), slice(tx * TILE, (tx + 1) * TILE)
        out[ys, xs], count[ys, xs] = tile_product(
            records, tile, factors, opaque[ys, xs], tx, ty
        )
    return out, count


def map_transmittance(scene, camera, materials, depth):
    """T (side, side, 3) of a sun map `depth` (side, side) from `camera`, in quadrants of
    FILL's frame as map_at draws it."""
    side = depth.shape[0]
    out = np.ones((side, side, 3), dtype=F)
    for j in range(side // FILL_SIDE):
        for i in range(side // FILL_SIDE):
            view = {
                "positions": scene["positions"],
                "indices": scene["indices"],
                "colors": np.zeros((len(scene["positions"]), 3), dtype=F),
                "camera": quadrant_camera(camera, i, j),
                "light": np.zeros(3, dtype=F),
            }
            rows, columns = (slice(FILL_SIDE * k, FILL_SIDE * (k + 1)) for k in (j, i))
            out[rows, columns] = transmittance(view, materials, depth[rows, columns])[0]
    return out


def t_channels(materials, triangles):
    """1 when every glass material among `triangles`' is grey (its tau's three channels
    equal), else 3."""
    rows = materials["material"][triangles]
    rows = np.unique(rows[materials["kind"][rows] == TRANSPARENT])
    tau = materials["transmission"][rows]
    return 1 if (tau == tau[:, :1]).all() else 3


def block_side(scale=T_SCALE):
    """Kept texels along a block's side: a map tile's (TILE x TILE map texels)."""
    return TILE // scale


def block_bytes(channels, scale=T_SCALE):
    """A block's bytes for `channels`: its texels' words."""
    return block_side(scale) ** 2 * WORD_BYTES[channels]


def kept(through, channels, scale=T_SCALE):
    """T (H, W, 3) as kept: {"codes" (h, w, channels) uint8, each the code of its scale x
    scale texels' float32 mean (pairs of rows summed, then the two sums; times 1 /
    scale^2; floor(255 v + 1/2)), "present" (tiles down, across) bool (a map tile's
    block not all 255), "scale", "channels"}; H and W multiples of TILE."""
    side_y, side_x = through.shape[:2]
    h, w = side_y // scale, side_x // scale
    blocks = through.reshape(h, scale, w, scale, 3).astype(F)
    low = blocks.sum(axis=1, dtype=F).sum(axis=2, dtype=F) if scale > 1 else through
    if scale > 1:
        low = (low.reshape(h, w, 3) * F(1.0 / (scale * scale))).astype(F)
    low = low[:, :, :1] if channels == 1 else low
    code = np.floor(low * F(255) + F(0.5))
    codes = np.clip(code, 0, 255).astype(np.uint8)
    k = block_side(scale)
    present = (codes.reshape(h // k, k, w // k, k, channels) != 255).any(axis=(1, 3, 4))
    return {"codes": codes, "present": present, "scale": scale, "channels": channels}


def kept_pages(form):
    """The 4 KiB pages a kept form holds (its blocks in map-tile order, as many a page
    as fit) and those with a present block."""
    per = PAGE_BYTES // block_bytes(form["channels"], form["scale"])
    present = form["present"].reshape(-1)
    pages = -(-len(present) // per)
    padded = np.zeros(pages * per, dtype=bool)
    padded[: len(present)] = present
    return pages, int(padded.reshape(pages, per).any(axis=1).sum())


def kept_at(form, iy, ix):
    """T (n, 3) float32 of the kept form at map texels iy, ix: code / 255 (a float32
    product), 1 in an absent block."""
    s, k = form["scale"], block_side(form["scale"])
    ky, kx = iy // s, ix // s
    codes = form["codes"][ky, kx].astype(F) * F(1.0 / 255)
    there = form["present"][ky // k, kx // k]
    return np.where(there[:, None], np.broadcast_to(codes, (len(ky), 3)), F(1))


def map_kept(scene, camera, materials, depth, scale=T_SCALE):
    """A sun map's T as kept (kept of map_transmittance), its channels by the scene's
    glass."""
    through = map_transmittance(scene, camera, materials, depth)
    channels = t_channels(materials, np.arange(len(scene["indices"])))
    return kept(through, channels, scale)


def sun_shares(lights, points, normals):
    """The sun's share (n, 3) float32 at points (n, 3) with normals (n, 3) through the
    map and its kept T ("shadow_transmit"): sun_shadow's four texels, each lit one
    weighted by its T, bilinear."""
    depth, through = lights["shadow_map"], lights["shadow_transmit"]
    sx, sy, w = sun_screen(
        lights["shadow_camera"], lights["shadow_texel"], points, normals
    )
    side = depth.shape[0]

    def lit_at(ix, iy):
        inside = (ix >= 0) & (ix < side) & (iy >= 0) & (iy < side)
        cy, cx = np.clip(iy, 0, side - 1), np.clip(ix, 0, side - 1)
        lit = ~(inside & (w < depth[cy, cx] - lights["shadow_bias"]))
        tint = np.where(inside[:, None], kept_at(through, cy, cx), F(1))
        return np.where(lit[:, None], tint, F(0))

    gx, gy = sx - F(0.5), sy - F(0.5)
    x0, y0 = np.floor(gx), np.floor(gy)
    fx, fy = (gx - x0)[:, None], (gy - y0)[:, None]
    x0, y0 = x0.astype(np.int64), y0.astype(np.int64)
    top = lit_at(x0, y0) * (F(1) - fx) + lit_at(x0 + 1, y0) * fx
    bottom = lit_at(x0, y0 + 1) * (F(1) - fx) + lit_at(x0 + 1, y0 + 1) * fx
    return top * (F(1) - fy) + bottom * fy
