"""The frames: the plain frame (setup, binning, fill), the FILL layers and SHADE, the
frame coloured from each pixel's material."""

import numpy as np

from prism_reference.material.kinds import (
    ALBEDO,
    EMISSIVE,
    FLAT,
    LIT,
    MASK,
    MASKED,
    NORMAL,
    OPAQUE_BYTE,
    SPECULAR,
    TRANSPARENT,
)
from prism_reference.material.texture import (
    TEXEL_LINEAR,
    TEXEL_SIGNED,
    TEXEL_UNIT,
    fetch,
    map_area,
    mapped_uv,
    mip_level,
    normal_scales,
    uv_maps,
)
from prism_reference.raster.fill import BACKGROUND, bin_triangles, fill_tile
from prism_reference.raster.setup import at, grid, setup
from prism_reference.raster.vector import cross3, dot3, normalized
from prism_reference.scene.frame import TILE, frame_size

F = np.float32
AMBIENT, DIFFUSE = F(0.25), F(0.75)  # the lit kind's ambient and diffuse weights


def picture(image, scene):
    """The picture of a rendered (padded) frame's image: its top-left W by H."""
    width, height = frame_size(scene)
    return image[:height, :width]


def rasterize(scene):
    """Colour (H, W, 3), 1/z (H, W), triangle index (H, W, -1 = none), tile counts
    (TY, TX), of the padded frame (setup.grid: H = TILE TY, W = TILE TX; `picture`)."""
    across, down = grid(scene)
    records = setup(scene)
    counts, offsets, members = bin_triangles(records, across, down)
    colour = np.empty((TILE * down, TILE * across, 3), dtype=np.float32)
    depth = np.empty((TILE * down, TILE * across), dtype=np.float32)
    tri = np.empty((TILE * down, TILE * across), dtype=np.int32)
    for t in range(across * down):
        ty, tx = divmod(t, across)
        c, d, win = fill_tile(records, members[offsets[t] : offsets[t + 1]], tx, ty)
        ys, xs = slice(ty * TILE, (ty + 1) * TILE), slice(tx * TILE, (tx + 1) * TILE)
        colour[ys, xs], depth[ys, xs] = c, d
        tri[ys, xs] = -1
        if len(records["tri"]):
            tri[ys, xs] = np.where(win >= 0, records["tri"][np.maximum(win, 0)], -1)
    return {
        "colour": colour,
        "depth": depth,
        "tri": tri,
        "tile_counts": counts.reshape(down, across),
    }


def layer_scene(scene, keep):
    """The scene with the triangles not in `keep` collapsed to their first corner
    (zero area: setup drops them), so the others keep their triangle numbers."""
    indices = scene["indices"].copy()
    indices[~keep] = indices[~keep][:, :1]
    return {**scene, "indices": indices}


def fill_layers(scene, materials, glass=True):
    """SHADE's FILLs: the layers of the triangles neither `masked` nor `transparent`,
    of the `masked` ones and of the `transparent` ones (empty without them or glass)."""
    kind = materials["kind"][materials["material"]]
    clear = kind == TRANSPARENT
    opaque = rasterize(layer_scene(scene, (kind != MASKED) & ~clear))
    masked = rasterize(layer_scene(scene, kind == MASKED))
    if glass and clear.any():
        return opaque, masked, rasterize(layer_scene(scene, clear))
    shape = opaque["depth"].shape
    empty = {
        "colour": np.broadcast_to(BACKGROUND, shape + (3,)).copy(),
        "depth": np.zeros(shape, dtype=np.float32),
        "tri": np.full(shape, -1, dtype=np.int32),
        "tile_counts": np.zeros_like(opaque["tile_counts"]),
    }
    return opaque, masked, empty


def glass_numbers(materials, layer, front):
    """Transmission tau (H, W, 3) of the glass layer's material where it is in front
    and its own surface's weight 1 - max(tau) (H, W, 1); both 0 elsewhere."""
    m = materials["material"][np.maximum(layer["tri"], 0)]
    tau = np.where(front[:, :, None], materials["transmission"][m], F(0))
    weight = np.where(front, F(1) - materials["transmission"][m].max(axis=2), F(0))
    return tau, weight[:, :, None]


def nearer_layer(first, second):
    """Where the first layer's fragment wins over the second's (larger 1/z, a tie to
    the lower triangle number; an empty second pixel always loses)."""
    return (first["tri"] >= 0) & (
        (first["depth"] > second["depth"])
        | ((first["depth"] == second["depth"]) & (first["tri"] < second["tri"]))
    )


def shade_setup(scene, materials):
    """Per triangle what SHADE needs (valid where `first` >= 0): "planes" (T, 3, 3) of
    u, v and light term times 1/z, "level" (T, 4) per slot (its uv map's area in,
    `texture.map_area`), the tangent "frame" (T, 3, 3) and "frame_ok"."""
    count = len(scene["indices"])
    extra = np.concatenate([materials["uv"], materials["light"][:, :, None]], axis=2)
    records = setup(scene, extra)
    first = np.full(count, -1, dtype=np.int64)
    first[records["tri"][::-1]] = np.arange(len(records["tri"]))[::-1]
    has = first >= 0
    pick = np.where(has, first, 0)
    planes_of = np.zeros((count, 3, 3), dtype=np.float32)
    level = np.zeros((count, 4), dtype=np.int32)
    if len(records["tri"]):
        planes_of = np.where(has[:, None, None], records["extra_planes"][pick], F(0))
        corner = records["extra"][pick]
        du1, dv1 = corner[:, 1, 0] - corner[:, 0, 0], corner[:, 1, 1] - corner[:, 0, 1]
        du2, dv2 = corner[:, 2, 0] - corner[:, 0, 0], corner[:, 2, 1] - corner[:, 0, 1]
        uv_area2 = np.abs(du1 * dv2 - du2 * dv1)
        texture = materials["textures"][materials["material"]]
        maps = uv_maps(materials)[materials["material"]]
        for slot in range(4):
            tex = np.maximum(texture[:, slot], 0)
            size = materials["mip"][tex, 0]
            texels = uv_area2 * (size[:, 1] * size[:, 2]).astype(np.float32)
            texels = texels * map_area(maps[:, slot])
            levels = np.where(texture[:, slot] >= 0, materials["levels"][tex], 1)
            level[:, slot] = mip_level(texels, records["area2"][pick], levels)
    p = scene["positions"][scene["indices"]]
    uv = materials["uv"]
    e1, e2 = p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]
    normal = normalized(cross3(e1, e2))
    to_eye = scene["camera"][None, 0:3] - p[:, 0]
    normal = np.where((dot3(normal, to_eye) < 0)[:, None], -normal, normal)
    du1, dv1 = uv[:, 1, 0] - uv[:, 0, 0], uv[:, 1, 1] - uv[:, 0, 1]
    du2, dv2 = uv[:, 2, 0] - uv[:, 0, 0], uv[:, 2, 1] - uv[:, 0, 1]
    det = du1 * dv2 - du2 * dv1
    sign = np.where(det < 0, F(-1), F(1))[:, None]
    tangent = (e1 * dv2[:, None] - e2 * dv1[:, None]) * sign
    bitangent = (e2 * du1[:, None] - e1 * du2[:, None]) * sign
    tangent = normalized(tangent - normal * dot3(normal, tangent)[:, None])
    side = cross3(normal, tangent)
    side = np.where((dot3(side, bitangent) < 0)[:, None], -side, side)
    frame_ok = (det != 0) & (dot3(tangent, tangent) > 0)
    return {
        "first": first,
        "planes": planes_of,
        "level": level,
        "frame": np.stack([tangent, side, normal], axis=1),
        "frame_ok": frame_ok,
    }


def power(x, exponent):
    """x ** exponent for integer exponents >= 1, by squaring (low bit first)."""
    result = np.ones_like(x)
    base = x.copy()
    e = exponent.copy()
    while (e > 0).any():
        odd = (e & 1) == 1
        result = np.where(odd, result * base, result)
        base = base * base
        e >>= 1
    return result


def pixel_values(layer, prepared, ys, xs):
    """Pixel centres, 1/z and the winner's u, v and light term at pixels (ys, xs)."""
    t = layer["tri"][ys, xs]
    px = xs.astype(np.float32) + F(0.5)
    py = ys.astype(np.float32) + F(0.5)
    w = layer["depth"][ys, xs]
    plane = prepared["planes"][t]
    u = at(plane[:, :, 0], px, py) / w
    v = at(plane[:, :, 1], px, py) / w
    light = at(plane[:, :, 2], px, py) / w
    return px, py, w, u, v, light


def shade_layer(scene, materials, prepared, layer):
    """Colour (H, W, 3) of one FILL layer by its winners' materials, and its holes
    (H, W) (masked pixels whose alpha byte is under OPAQUE_BYTE)."""
    colour = layer["colour"].copy()
    hole = np.zeros(layer["tri"].shape, dtype=bool)
    ys, xs = np.nonzero(layer["tri"] >= 0)
    t = layer["tri"][ys, xs]
    m = materials["material"][t]
    kind = materials["kind"][m]
    shaded = kind != FLAT
    ys, xs, t, m, kind = ys[shaded], xs[shaded], t[shaded], m[shaded], kind[shaded]
    px, py, w, u, v, light = pixel_values(layer, prepared, ys, xs)
    texture = materials["textures"][m]
    level = prepared["level"][t]
    base = materials["base_colour"][m]
    maps = uv_maps(materials)[m]

    def texel(slot):
        if len(materials["mip"]) == 0:
            return np.zeros((len(u), 4), dtype=np.uint8)
        tex = np.maximum(texture[:, slot], 0)
        su, sv = mapped_uv(maps[:, slot], u, v)
        return fetch(materials, tex, level[:, slot], su, sv)

    albedo_texel = texel(ALBEDO)
    albedo = np.where(
        (texture[:, ALBEDO] >= 0)[:, None],
        TEXEL_LINEAR[albedo_texel[:, :3]] * base,
        base,
    )
    out = albedo * light[:, None]
    lit = kind == LIT
    if lit.any():
        out[lit] = shade_lit(
            scene, materials, prepared, t, m, px, py, w, texel, albedo
        )[lit]
    out = np.where((kind == EMISSIVE)[:, None], albedo, out)
    masked = kind == MASKED
    albedo_alpha = np.where(texture[:, ALBEDO] >= 0, albedo_texel[:, 3], 255)
    alpha = np.where(texture[:, MASK] >= 0, texel(MASK)[:, 3], albedo_alpha)
    hole[ys, xs] = masked & (alpha < OPAQUE_BYTE)
    colour[ys, xs] = out
    return colour, hole


def shade_lit(scene, materials, prepared, t, m, px, py, w, texel, albedo):
    """The lit kind's colour: albedo (ambient + diffuse) + Blinn-Phong specular from
    the scene's point light, with the normal map's normal in the triangle's frame."""
    cam = scene["camera"]
    z = F(1) / w
    xc = ((px - cam[13]) / cam[12]) * z
    yc = ((cam[14] - py) / cam[12]) * z
    position = np.stack(
        [
            ((cam[k] + cam[3 + k] * xc) + cam[6 + k] * yc) + cam[9 + k] * z
            for k in range(3)
        ],
        axis=-1,
    )
    to_light = normalized(scene["light"][None, :] - position)
    to_eye = normalized(cam[None, 0:3] - position)
    half = normalized(to_light + to_eye)
    frame = prepared["frame"][t]
    texture = materials["textures"][m]
    mapped = (texture[:, NORMAL] >= 0) & prepared["frame_ok"][t]
    n_texel = TEXEL_SIGNED[texel(NORMAL)[:, :3]] * normal_scales(materials)[m]
    bent = normalized(
        (frame[:, 0] * n_texel[:, 0:1] + frame[:, 1] * n_texel[:, 1:2])
        + frame[:, 2] * n_texel[:, 2:3]
    )
    normal = np.where(mapped[:, None], bent, frame[:, 2])
    diffuse = np.maximum(dot3(normal, to_light), F(0))
    gloss = power(np.maximum(dot3(normal, half), F(0)), materials["exponent"][m])
    specular = np.where(
        (texture[:, SPECULAR] >= 0)[:, None],
        materials["specular"][m] * TEXEL_UNIT[texel(SPECULAR)[:, :3]],
        materials["specular"][m],
    )
    return albedo * (AMBIENT + DIFFUSE * diffuse)[:, None] + specular * gloss[:, None]


def rasterize_shaded(scene, materials):
    """SHADE after three FILLs: colour, the surface behind the glass (1/z, triangle),
    the tile counts added, the layers and where the glass is in front ("front")."""
    opaque, masked, glass = fill_layers(scene, materials)
    prepared = shade_setup(scene, materials)
    opaque_colour, _ = shade_layer(scene, materials, prepared, opaque)
    masked_colour, hole = shade_layer(scene, materials, prepared, masked)
    take = nearer_layer(masked, opaque) & ~hole
    colour = np.where(take[:, :, None], masked_colour, opaque_colour)
    depth = np.where(take, masked["depth"], opaque["depth"])
    tri = np.where(take, masked["tri"], opaque["tri"])
    front = nearer_layer(glass, {"depth": depth, "tri": tri})
    if front.any():
        glass_colour, _ = shade_layer(scene, materials, prepared, glass)
        tau, weight = glass_numbers(materials, glass, front)
        mixed = tau * colour + weight * glass_colour
        colour = np.where(front[:, :, None], mixed, colour)
    counts = opaque["tile_counts"] + masked["tile_counts"] + glass["tile_counts"]
    return {
        "colour": colour,
        "depth": depth,
        "tri": tri,
        "tile_counts": counts,
        "opaque": opaque,
        "masked": masked,
        "glass": glass,
        "front": front,
    }
