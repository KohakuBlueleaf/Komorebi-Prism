"""LIGHT's checks on arrays: the frame from the planes, the surface planes and the glass's,
the field's sparse lookups, the lit frame, and the sun's shadow map."""

import numpy as np

from prism.stages.direct.light.model.frame import (
    angle_degrees,
    figures,
    frame_from_planes,
)
from prism.stages.direct.light.model.numbers import F32
from prism.stages.direct.light.model.sun import quadrant_cameras
from prism.stages.direct.light.model.surface import (
    light_reference,
    reference_surface,
    shadow_band,
)
from prism.stages.material.texture.model.layers import later_pieces
from prism_reference.direct.frame import TERMS
from prism_reference.direct.lights import placeholder, shadow_side
from prism_reference.direct.shadow import FILL_SIDE, shadow_map
from prism_reference.indirect.field.build import voxel_keys
from prism_reference.indirect.field.values import FIELD_SHIFT
from prism_reference.indirect.light import field_for
from prism_reference.post.display import to_srgb8
from prism_reference.raster.frames import picture, rasterize_shaded, shade_setup
from prism_reference.raster.setup import setup, world_points


def with_map(view, materials, lights):
    """`lights` with their shadow map: a placeholder (the sun above the horizon) made
    by shadow_map at their sun and side now; else as they are."""
    if not placeholder(lights) or lights["sun_direction"][1] <= 0:
        return lights
    side = shadow_side(lights)
    depth, _, _ = shadow_map(view, lights["sun_direction"], materials, side)
    return {**lights, "shadow_map": depth}


def frame_check(name, scene, materials, samples, seed=1):
    """The frame from each record's planes against the reference's (shade_setup) for
    `samples` records of the scene `name` (`scene`, `materials`): whole triangles and
    first pieces of cut ones apart, angles in degrees."""
    extra = np.concatenate([materials["uv"], materials["light"][:, :, None]], axis=2)
    records = setup(scene, extra)
    prepared = shade_setup(scene, materials)
    owner = records["tri"]
    first = np.r_[True, owner[1:] != owner[:-1]]
    cut = np.zeros(len(owner), dtype=bool)
    cut[1:] |= owner[1:] == owner[:-1]
    cut[:-1] |= owner[1:] == owner[:-1]
    frame, valid = frame_from_planes(
        scene["camera"],
        records["w_planes"],
        records["extra_planes"][:, :, 0],
        records["extra_planes"][:, :, 1],
    )
    want = prepared["frame"][owner]
    want_ok = prepared["frame_ok"][owner]
    rng = np.random.default_rng(seed)
    report = {"scene": name, "records": len(owner)}
    for label, chosen in (("whole", first & ~cut), ("first_of_cut", first & cut)):
        index = np.flatnonzero(chosen)
        if len(index) > samples:
            index = np.sort(rng.choice(index, samples, replace=False))
        both = valid[index] & want_ok[index]
        part = {
            "records": len(index),
            "valid_differs": int((valid[index] != want_ok[index]).sum()),
            "reference_not_valid": int((~want_ok[index]).sum()),
            "normal": figures(angle_degrees(frame[index, 2], want[index, 2])),
        }
        for axis, key in ((0, "tangent"), (1, "bitangent")):
            part[key] = figures(
                angle_degrees(frame[index[both], axis], want[index[both], axis])
            )
        report[label] = part
    return report


def glass_check(view, materials, lights, got, glass_got, want):
    """The card's glass planes in front (bit 31 clear, 1/z over `got`'s) against the
    reference's glass parts: front pixels each side, then on both (later pieces apart)
    1/z error, material, normal, ties."""
    parts = want["parts"]
    card_front = ((glass_got["material"] >> 31) == 0) & (
        glass_got["depth"].view(np.uint32) > got["depth"].view(np.uint32)
    )
    ties = ((glass_got["material"] >> 31) == 0) & (
        glass_got["depth"].view(np.uint32) == got["depth"].view(np.uint32)
    )
    front = parts["glass_tri"] >= 0
    corner = {**materials, "light": lights["visibility"][view["indices"]]}
    later = later_pieces(view, corner, parts["glass_tri"])
    both = front & card_front & ~later
    with np.errstate(all="ignore"):
        relative = np.abs(
            glass_got["depth"].astype(np.float64) - parts["glass_depth"]
        ) / np.abs(parts["glass_depth"].astype(np.float64))
    material = glass_got["material"] & 0xFFFF
    angle = angle_degrees(glass_got["normal"], parts["glass_normal"])
    return {
        "front_reference": int(front.sum()),
        "front_card": int(card_front.sum()),
        "front_only_reference": int((front & ~card_front).sum()),
        "front_only_card": int((card_front & ~front).sum()),
        "ties_on_card": int(ties.sum()),
        "later_pieces": int((front & later).sum()),
        "checked": int(both.sum()),
        "depth_relative_max": float(relative[both].max(initial=0)),
        "depth_relative_over_1e-5": int((relative[both] > 1e-5).sum()),
        "material_differ": int((material[both] != parts["glass_material"][both]).sum()),
        "normal_degrees": figures(angle[both]),
    }


def surface_check(view, materials, lights, got, glass_got=None):
    """The card's surface `got` (decode_planes' images) against the reference's for the
    pixels the reference covers, later pieces counted apart; with `glass_got` the glass
    layer's planes too (glass_check). Over the padded frame."""
    want = reference_surface(view, materials, lights)
    covered = want["tri"] >= 0
    groups = {
        "checked": covered & ~want["later"],
        "later_pieces": covered & want["later"],
    }
    to8 = lambda x: np.clip(np.floor(x * F32(255) + F32(0.5)), 0, 255)
    a_error = np.abs(to8(got["a"]) - to8(want["a"])).max(axis=2)
    angle = angle_degrees(got["normal"], want["normal"])
    vis_error = np.abs(got["visibility"] - want["visibility"])
    spec_error = np.abs(to8(got["specular"]) - to8(want["specular"])).max(axis=2)
    material_differs = got["material"] != want["material"]
    empty_differs = (want["tri"] < 0) & ((got["material"] >> 31) == 0)
    report = {"empty_marked_differ": int(empty_differs.sum())}
    for name, chosen in groups.items():
        count = max(int(chosen.sum()), 1)
        report[name] = {
            "pixels": int(chosen.sum()),
            "a_over_2_of_255": int((a_error[chosen] > 2).sum()),
            "a_max_of_255": int(a_error[chosen].max(initial=0)),
            "normal_degrees": figures(angle[chosen]),
            "normal_share_over_2deg": round(
                float((angle[chosen] > 2).sum() / count), 6
            ),
            "visibility_over_1_of_255": int((vis_error[chosen] > 1 / 255).sum()),
            "specular_over_2_of_255": int((spec_error[chosen] > 2).sum()),
            "material_differ": int(material_differs[chosen].sum()),
        }
    part = report["checked"]
    report["all_within"] = bool(
        part["a_over_2_of_255"] == 0
        and part["visibility_over_1_of_255"] == 0
        and part["material_differ"] == 0
        and report["empty_marked_differ"] == 0
    )
    if glass_got is not None:
        report["glass"] = glass_check(view, materials, lights, got, glass_got, want)
    return report, want


def field_sparse(view, lights, lit):
    """The pixels whose field lookup (at the reference's point and normal of `lit`, the
    surface behind any glass) found fewer than 8 of its voxels with data in a direction
    the normal faces."""
    model, _ = field_for(lights)
    tri = lit["tri"]
    ys, xs = np.nonzero(tri >= 0)
    px, py = xs.astype(F32) + F32(0.5), ys.astype(F32) + F32(0.5)
    position = world_points(view["camera"], px, py, lit["depth"][ys, xs])
    n = lit["parts"]["normal"][ys, xs].astype(F32)
    h, origin, dims = model["field_spacing"], model["field_origin"], model["field_dims"]
    keys, has = model["field_keys"], model["field_has"]
    g = ((position + n * (F32(FIELD_SHIFT) * h)) - origin) / h - F32(0.5)
    base = np.floor(g).astype(np.int64)
    found = np.zeros(len(n), dtype=np.int64)
    for corner in np.ndindex(2, 2, 2):
        key = voxel_keys(base + np.array(corner), dims)
        at = np.minimum(np.searchsorted(keys, key), len(keys) - 1)
        ok = (keys[at] == key) & (key >= 0)
        faced = np.zeros(len(n), dtype=bool)
        for axis in range(3):
            faced |= has[at, 2 * axis + (n[:, axis] < 0)]
        found += ok & faced
    sparse = np.zeros(tri.shape, dtype=bool)
    sparse[ys, xs] = found < 8
    return sparse


def light_check(view, materials, lights, got, terms=TERMS):
    """The card's 8-bit picture (the view's size) against light_reference's: shares of
    pixels off by more than 2, 4, 8 in a channel, later pieces apart; with the shadow,
    the same inside the sun's shadow edge band and outside; with the field, by its
    sparse lookups."""
    lights = with_map(view, materials, lights)
    lit = light_reference(view, materials, lights, terms)

    def crop(image):
        return picture(image, view)

    want = to_srgb8(crop(lit["display"]))
    error = np.abs(got[..., :3].astype(np.int16) - want.astype(np.int16)).max(axis=2)
    corner = {**materials, "light": lights["visibility"][view["indices"]]}
    apart = later_pieces(view, corner, lit["tri"])
    front = lit["parts"]["glass_tri"] >= 0
    if front.any():
        apart = apart | later_pieces(view, corner, lit["parts"]["glass_tri"])
    apart, front = crop(apart), crop(front)
    checked = ~apart
    count = max(int(checked.sum()), 1)
    report = {"checked": int(checked.sum()), "later_pieces": int(apart.sum())}
    for limit in (2, 4, 8):
        report[f"share_over_{limit}"] = round(
            float((error[checked] > limit).sum() / count), 6
        )
        report[f"later_over_{limit}"] = int((error[apart] > limit).sum())
    report["max_error"] = int(error[checked].max(initial=0))
    glass = checked & front
    report["glass_in_front"] = {"pixels": int(front.sum()), "checked": int(glass.sum())}
    for limit in (2, 4, 8):
        report["glass_in_front"][f"share_over_{limit}"] = round(
            float((error[glass] > limit).sum() / max(int(glass.sum()), 1)), 6
        )
    report["glass_in_front"]["max_error"] = int(error[glass].max(initial=0))
    parts = []
    if "shadow" in terms:
        band = crop(shadow_band(view, lights, lit))
        parts += [("band", checked & band), ("outside_band", checked & ~band)]
    if "indirect" in terms:
        sparse = crop(field_sparse(view, lights, lit))
        parts += [("field_under_8", checked & sparse), ("field_8", checked & ~sparse)]
    for name, chosen in parts:
        part = {"pixels": int(chosen.sum())}
        for limit in (2, 4, 8):
            part[f"over_{limit}"] = int((error[chosen] > limit).sum())
            part[f"share_over_{limit}"] = round(
                float((error[chosen] > limit).sum() / max(int(chosen.sum()), 1)), 6
            )
        report[name] = part
    report["ok"] = report["share_over_4"] < 0.01
    return report, want


def sun_check(view, materials, lights, got):
    """The card's shadow map `got` against rasterize_shaded at each quadrant's camera of
    `lights`' shadow camera: texels over 1e-5 relative apart and texels empty on one
    side only, by the reference's layer and by quadrant; later pieces apart."""
    lights = with_map(view, materials, lights)
    side = shadow_side(lights)
    fill = FILL_SIDE
    want = np.zeros((side, side), dtype=F32)
    tri = np.full((side, side), -1, dtype=np.int32)
    masked_tri = np.full((side, side), -1, dtype=np.int32)
    later = np.zeros((side, side), dtype=bool)
    corner = {**materials, "light": lights["visibility"][view["indices"]]}
    cameras = quadrant_cameras(lights["shadow_camera"], side)
    for quadrant, camera in enumerate(cameras):
        sun_view = {
            "positions": view["positions"],
            "indices": view["indices"],
            "colors": np.zeros((len(view["positions"]), 3), dtype=np.float32),
            "camera": camera,
            "light": np.zeros(3, dtype=np.float32),
            "depth_view": True,
        }
        shaded = rasterize_shaded(sun_view, materials)
        j, i = divmod(quadrant, side // fill)
        place = (slice(fill * j, fill * (j + 1)), slice(fill * i, fill * (i + 1)))
        want[place], tri[place] = shaded["depth"], shaded["tri"]
        masked_tri[place] = shaded["masked"]["tri"]
        owner = setup(sun_view)["tri"]
        if (owner[1:] == owner[:-1]).any():
            later[place] = later_pieces(sun_view, corner, shaded["tri"])
    report = {
        "side": side,
        "reference_equals_moved": bool(
            np.array_equal(want.view(np.uint32), lights["shadow_map"].view(np.uint32))
        ),
    }
    taken_masked = (masked_tri >= 0) & (tri == masked_tri)
    with np.errstate(all="ignore"):
        relative = np.abs(got.astype(np.float64) - want) / np.abs(
            want.astype(np.float64)
        )
    both = (got != 0) & (want != 0)
    differs = both & (relative > 1e-5)
    one_empty = (got == 0) != (want == 0)
    report["later_pieces"] = int(later.sum())
    report["texels_covered"] = int((want != 0).sum())
    groups = {
        "all": ~later,
        "opaque_layer": ~later & (tri >= 0) & ~taken_masked,
        "masked_layer": ~later & taken_masked,
        "empty_in_reference": ~later & (tri < 0),
    }
    for name, chosen in groups.items():
        count = max(int(chosen.sum()), 1)
        report[name] = {
            "texels": int(chosen.sum()),
            "differ_over_1e-5": int((differs & chosen).sum()),
            "share_differ": round(float((differs & chosen).sum() / count), 7),
            "one_empty": int((one_empty & chosen).sum()),
            "share_one_empty": round(float((one_empty & chosen).sum() / count), 7),
        }
    report["max_relative"] = float(relative[both & ~later].max(initial=0))
    quadrant_of = (np.arange(side) // fill)[:, None] * (side // fill) + (
        np.arange(side) // fill
    )[None, :]
    report["by_quadrant"] = [
        {
            "differ_over_1e-5": int((differs & ~later & (quadrant_of == q)).sum()),
            "one_empty": int((one_empty & ~later & (quadrant_of == q)).sum()),
        }
        for q in range(len(cameras))
    ]
    return report
