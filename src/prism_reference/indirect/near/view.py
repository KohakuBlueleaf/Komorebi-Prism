"""A view's frame as the near field reads it, rasterized by the reference, and its
one-tile operator W_T at half rows."""

import numpy as np

from prism_reference.direct.frame import rasterize_lighted
from prism_reference.indirect.elements import triangle_geometry
from prism_reference.indirect.field.values import field_values
from prism_reference.indirect.hmatrix.apply import apply
from prism_reference.indirect.near.fuse import near_frame, near_operator
from prism_reference.indirect.near.half import half_camera, half_of, half_settings
from prism_reference.indirect.near.march import SETTINGS
from prism_reference.indirect.near.one_tile import FORM, tile_operator
from prism_reference.material.kinds import EMISSIVE
from prism_reference.raster.setup import world_points

F = np.float32
# The march at half resolution: two slices, the one-tile form's tile.
HALF = {**SETTINGS, "slices": 2, "tile": FORM["tile"]}


def view_frame(scene, materials, lights, terms=("ambient",)):
    """The view's camera, covered (H, W), world position, shading and geometric normal
    (H, W, 3; the geometric one facing the eye), the emissive pixels and the linear
    colour lit by `terms`."""
    lit = rasterize_lighted(scene, materials, lights, terms=terms)
    tri, depth = lit["tri"], lit["depth"]
    cam = scene["camera"]
    covered = tri >= 0
    ys, xs = np.nonzero(covered)
    t = tri[ys, xs]
    position = np.zeros(tri.shape + (3,), F)
    position[ys, xs] = world_points(cam, xs + F(0.5), ys + F(0.5), depth[ys, xs])
    _, _, flat = triangle_geometry(scene)
    g = flat[t].astype(F)
    g = np.where(((g * (cam[None, 0:3] - position[ys, xs])).sum(1) < 0)[:, None], -g, g)
    geometric = np.zeros_like(position)
    geometric[ys, xs] = g
    normal = np.where(covered[..., None], lit["parts"]["normal"], 0).astype(F)
    kind = materials["kind"][materials["material"]]
    glow = np.zeros(tri.shape, bool)
    glow[ys, xs] = kind[t] == EMISSIVE
    return {
        "camera": cam,
        "covered": covered,
        "position": position,
        "normal": normal,
        "geometric": geometric,
        "glow": glow,
        "colour": lit["colour"],
    }


def furnace_values(model):
    """The field's values (entries, 3) of the white furnace: every element's radiance
    and the sky 1, the transport's one apply."""
    real = model["real"][:, None].astype(F)
    sky = np.zeros((25, 3), F)
    sky[0] = F(np.sqrt(4 * np.pi))
    e = apply(model["blocks"], model["weights"], np.repeat(real, 3, 1))
    return field_values(model, (e + np.maximum(model["transfer"] @ sky, F(0))) * real)


def view_operator(frame, model, furnace, workers=1):
    """W_T at half rows of `frame` (view_frame) with the field `model` and its furnace
    values (entries, 3), and the half frame it was marched on (by `workers`)."""
    settings = half_settings(HALF)
    half = {
        k: half_of(frame[k]) for k in ("position", "normal", "geometric", "covered")
    }
    marched = near_frame(
        half_camera(frame["camera"]),
        half["position"],
        half["normal"],
        half["geometric"],
        half["covered"],
        settings["coarse_level"],
    )
    receivers = half_of(frame["covered"] & ~frame["glow"])
    spacing = float(model["field_spacing"])
    op = near_operator(marched, receivers, spacing, None, settings, None, workers)
    t_op = tile_operator(
        op,
        marched,
        half["covered"],
        half["position"],
        half["normal"],
        model,
        furnace,
        None,
        workers,
    )
    return t_op, marched
