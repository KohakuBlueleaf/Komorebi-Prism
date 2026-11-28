"""The lit frame: SHADE's three FILLs with direct light (sky, ambient, sun and its
shadow, lamps, specular), the background, glass and the optional indirect term."""

import numpy as np

from prism_reference.direct.glass import (
    GLASS_LIGHT,
    glass_over,
    sun_glass_map,
    sun_through,
)
from prism_reference.direct.lamps import lamp_irradiance_at
from prism_reference.direct.shadow import sun_shadow
from prism_reference.direct.sky import background, sky_irradiance
from prism_reference.direct.transmit import sun_shares
from prism_reference.direct.visibility import vertex_normals
from prism_reference.indirect.light import field_for, irradiance
from prism_reference.material.kinds import (
    ALBEDO,
    EMISSIVE,
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
    filtered_exponent,
    mapped_uv,
    normal_length,
    normal_scales,
    uv_maps,
)
from prism_reference.post.tone import CURVE_PLAIN, tone
from prism_reference.raster.fill import BACKGROUND
from prism_reference.raster.frames import (
    fill_layers,
    glass_numbers,
    nearer_layer,
    pixel_values,
    power,
    shade_setup,
)
from prism_reference.raster.setup import at, setup, world_points
from prism_reference.raster.vector import dot3, normalized

F = np.float32
# The terms of the colour (all by default) and the one off by default (bounced light).
TERMS = ("sky", "ambient", "sun", "shadow", "lamps", "specular", "background", "glass")
OPTIONAL_TERMS = ("indirect", GLASS_LIGHT)


def smooth_setup(scene):
    """Per triangle the planes (T, 3, 3) of its corners' area-weighted vertex normals
    times 1/z, of its first kept piece (as `shade_setup`): the smooth-normal variant."""
    normals = vertex_normals(scene["positions"], scene["indices"])
    records = setup(scene, normals[scene["indices"]])
    count = len(scene["indices"])
    first = np.full(count, -1, dtype=np.int64)
    first[records["tri"][::-1]] = np.arange(len(records["tri"]))[::-1]
    pick = np.maximum(first, 0)
    return np.where((first >= 0)[:, None, None], records["extra_planes"][pick], F(0))


def light_layer(scene, materials, prepared, layer, lights, variant):
    """Linear colour (H, W, 3) of one FILL layer under the lights (the terms in
    variant["terms"]), its holes, and the parts."""
    shape = layer["tri"].shape
    terms = variant["terms"]
    colour = np.zeros(shape + (3,), dtype=np.float32)
    parts = {
        k: np.zeros(shape + (3,), dtype=np.float32)
        for k in ("sky", "sun", "points", "albedo", "normal", "specular")
    }
    parts["visibility"] = np.zeros(shape, dtype=np.float32)
    parts["material"] = np.full(shape, -1, dtype=np.int32)
    hole = np.zeros(shape, dtype=bool)
    ys, xs = np.nonzero(layer["tri"] >= 0)
    t = layer["tri"][ys, xs]
    m = materials["material"][t]
    kind = materials["kind"][m]
    px, py, w, u, v, vis = pixel_values(layer, prepared, ys, xs)
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
    cam = scene["camera"]
    position = world_points(cam, px, py, w)
    to_eye = normalized(cam[None, 0:3] - position)
    frame = prepared["frame"][t]
    if variant.get("smooth") is not None:
        smooth = normalized(
            np.stack(
                [at(variant["smooth"][t][:, :, k], px, py) / w for k in range(3)], -1
            )
        )
        smooth = np.where((dot3(smooth, to_eye) < 0)[:, None], -smooth, smooth)
        frame = np.stack([frame[:, 0], frame[:, 1], smooth], axis=1)
    mapped = (texture[:, NORMAL] >= 0) & prepared["frame_ok"][t]
    stored = TEXEL_SIGNED[texel(NORMAL)[:, :3]]
    n_texel = stored * normal_scales(materials)[m]
    bent = normalized(
        (frame[:, 0] * n_texel[:, 0:1] + frame[:, 1] * n_texel[:, 1:2])
        + frame[:, 2] * n_texel[:, 2:3]
    )
    normal = np.where(mapped[:, None], bent, frame[:, 2])
    glass = kind == TRANSPARENT
    emissive = kind == EMISSIVE
    normal = np.where(glass[:, None], prepared["frame"][t][:, 2], normal)
    length = np.where(mapped & ~glass, normal_length(stored), F(1))
    albedo = np.where(emissive[:, None], albedo, albedo * length[:, None])
    has_specular = ((kind == LIT) | glass) & (materials["specular"][m].max(axis=1) > 0)
    specular = np.where(
        (texture[:, SPECULAR] >= 0)[:, None],
        materials["specular"][m] * TEXEL_UNIT[texel(SPECULAR)[:, :3]],
        materials["specular"][m],
    )
    specular = np.where(has_specular[:, None], specular, F(0))
    if "specular" not in terms:
        specular = np.zeros_like(specular)
    exponent, lobe = filtered_exponent(materials["exponent"][m], length)
    specular = specular * lobe[:, None]
    inv_pi = F(1 / np.pi)

    def gloss(to_light):
        half = normalized(to_light + to_eye)
        return power(np.maximum(dot3(normal, half), F(0)), exponent)

    zero = np.zeros_like(albedo)
    sky = zero
    if "sky" in terms and "indirect" not in terms:
        sky = np.maximum(sky_irradiance(lights["sh"], normal), F(0))
        sky = sky * vis[:, None]
    sun_dir = lights["sun_direction"]
    sun_e = zero
    if "sun" in terms:
        shadow = np.ones((len(position), 1), dtype=np.float32)
        if "shadow" in terms and "shadow_transmit" in lights:
            shadow = sun_shares(lights, position, normal)
        elif "shadow" in terms:
            shadow = sun_shadow(lights, position, normal, variant["pcf"])[:, None]
        facing = np.maximum(dot3(normal, sun_dir[None, :]), F(0))[:, None]
        sun_e = lights["sun_irradiance"] * (facing * shadow)
        if variant.get("sun_glass") is not None:
            through = sun_through(lights, variant["sun_glass"], position, normal)
            sun_e = sun_e * np.where(glass[:, None], F(1), through)
    shine = specular * gloss(sun_dir[None, :])[:, None] * (sun_e * inv_pi)
    points_e = np.zeros_like(albedo)
    for k in range(len(lights["lamp_intensity"]) if "lamps" in terms else 0):
        e, to_light = lamp_irradiance_at(lights, k, position, normal)
        lamp_e = lights["lamp_colour"][k] * e[:, None]
        points_e = points_e + lamp_e
        shine = shine + specular * gloss(to_light)[:, None] * (lamp_e * inv_pi)
    ambient = np.asarray(lights["ambient"], dtype=np.float32)
    if "ambient" not in terms or "indirect" in terms:
        ambient = np.zeros(3, dtype=np.float32)
    light_sum = ((sky + ambient) + sun_e) + points_e
    if "indirect" in terms:
        bounce = variant["indirect"](position, normal)
        light_sum = (bounce + sun_e) + points_e
    out = albedo * inv_pi * light_sum
    if glass.any():
        own = F(1) - materials["transmission"][m].max(axis=1)
        out = out * np.where(glass, own, F(1))[:, None]
    out = out + shine
    out = np.where(emissive[:, None], albedo * F(lights["emissive_scale"]), out)
    lit_parts = {
        "sky": albedo * inv_pi * sky,
        "sun": albedo * inv_pi * sun_e,
        "points": albedo * inv_pi * points_e,
    }
    if "indirect" in terms:
        lit_parts["indirect"] = albedo * inv_pi * bounce
        parts.setdefault("indirect", np.zeros(shape + (3,), dtype=np.float32))
    for name, value in lit_parts.items():
        parts[name][ys, xs] = np.where(emissive[:, None], F(0), value)
    parts["visibility"][ys, xs] = vis
    parts["albedo"][ys, xs] = albedo
    parts["normal"][ys, xs] = normal
    parts["specular"][ys, xs] = specular
    parts["material"][ys, xs] = m
    masked = kind == MASKED
    albedo_alpha = np.where(texture[:, ALBEDO] >= 0, albedo_texel[:, 3], 255)
    alpha = np.where(texture[:, MASK] >= 0, texel(MASK)[:, 3], albedo_alpha)
    hole[ys, xs] = masked & (alpha < OPAQUE_BYTE)
    colour[ys, xs] = out
    return colour, hole, parts


def rasterize_lighted(scene, materials, lights, smooth=False, pcf=True, terms=TERMS):
    """SHADE's three FILLs and holes with direct light; terms of TERMS and "indirect".
    "colour" linear, "display" its `tone`, the parts; smooth: vertex normals; pcf=False:
    one shadow tap."""
    opaque, masked, glass = fill_layers(scene, materials, "glass" in terms)
    corner_vis = lights["visibility"][scene["indices"]]
    prepared = shade_setup(scene, {**materials, "light": corner_vis})
    variant = {"smooth": smooth_setup(scene) if smooth else None, "pcf": pcf}
    variant["terms"] = set(terms)
    unknown = variant["terms"] - set(TERMS) - set(OPTIONAL_TERMS)
    if unknown:
        raise ValueError(f"unknown lighting terms {sorted(unknown)}")
    if "indirect" in variant["terms"]:
        field_for(lights)
        variant["indirect"] = lambda p, n: irradiance(lights, p, n)
    through = {"sun", "shadow", "glass", GLASS_LIGHT} <= variant["terms"]
    through = through and bool((glass["tri"] >= 0).any())
    through = through and "shadow_transmit" not in lights  # the map's T carries it
    variant["sun_glass"] = sun_glass_map(scene, materials, lights) if through else None
    opaque_colour, _, opaque_parts = light_layer(
        scene, materials, prepared, opaque, lights, variant
    )
    masked_colour, hole, masked_parts = light_layer(
        scene, materials, prepared, masked, lights, variant
    )
    take = nearer_layer(masked, opaque) & ~hole
    tri = np.where(take, masked["tri"], opaque["tri"])
    sky = (tri < 0)[:, :, None]
    colour = np.where(take[:, :, None], masked_colour, opaque_colour)
    behind = BACKGROUND
    if "background" in variant["terms"]:
        behind = background(scene, lights)
    colour = np.where(sky, behind, colour)
    parts = {}
    for name in opaque_parts:
        pick = take if opaque_parts[name].ndim == 2 else take[:, :, None]
        parts[name] = np.where(pick, masked_parts[name], opaque_parts[name])
    depth = np.where(take, masked["depth"], opaque["depth"])
    parts["depth"] = depth
    parts["layer"] = np.where(tri < 0, -1, take.astype(np.int32)).astype(np.int8)
    front = nearer_layer(glass, {"depth": depth, "tri": tri})
    parts["glass_depth"] = np.where(front, glass["depth"], F(0))
    parts["glass_tri"] = np.where(front, glass["tri"], -1).astype(np.int32)
    parts["glass_material"] = np.full(tri.shape, -1, dtype=np.int32)
    parts["glass_normal"] = np.zeros(tri.shape + (3,), dtype=np.float32)
    if front.any():
        own, _, glass_parts = light_layer(
            scene, materials, prepared, glass, lights, variant
        )
        tau, _ = glass_numbers(materials, glass, front)
        behind = (colour, own, tau)
        field = variant.get("indirect")
        colour = glass_over(
            scene, lights, glass, glass_parts, front, behind, terms, field
        )
        parts["glass_material"] = np.where(front, glass_parts["material"], -1)
        parts["glass_normal"] = np.where(front[:, :, None], glass_parts["normal"], F(0))
    display = tone(
        colour,
        lights["exposure"],
        lights.get("saturation", 1.0),
        lights.get("curve", CURVE_PLAIN),
    )
    return {
        "colour": colour,
        "display": display,
        "depth": depth,
        "tri": tri,
        "parts": parts,
    }
