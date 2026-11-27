"""Each material's texture slots against the triangles' stored uv: the uv set a material
reads (its base colour's), the 2 x 3 map from the stored uv to each slot's own uv (the
slot's KHR_texture_transform), and the normal map's scale."""

import numpy as np

from prism_reference.material.kinds import ALBEDO, NORMAL

FLIP = np.array([[1.0, 0.0, 0.0], [0.0, -1.0, 1.0], [0.0, 0.0, 1.0]])  # (u, 1 - v)


def use_matrix(use):
    """The 3 x 3 map of a TextureUse's transform on (u, v, 1): scale, then rotation,
    then offset (`convert.transformed`); the identity without one."""
    if use is None:
        return np.eye(3)
    c, s = np.cos(use.rotation), np.sin(use.rotation)
    rotate = np.array([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]])
    scale = np.diag([use.scale[0], use.scale[1], 1.0])
    offset = np.array([[1.0, 0.0, use.offset[0]], [0.0, 1.0, use.offset[1]], [0, 0, 1]])
    return offset @ rotate @ scale


def stored_use(material):
    """The TextureUse the triangles' stored uv follows: the base colour's."""
    return material.base_color_texture


def uv_set(material):
    """The uv set (0 or 1) a material's triangles store: its base colour's."""
    use = stored_use(material)
    return 0 if use is None else int(use.uv)


def slot_uses(material, kind):
    """{slot: TextureUse} of the slots a material's record samples."""
    uses = {ALBEDO: material.base_color_texture, NORMAL: material.normal_texture}
    if kind == "emissive" and material.emissive_texture is not None:
        uses[ALBEDO] = material.emissive_texture
    return uses


def slot_maps(material, kind):
    """(4, 2, 3) per slot the map from the stored (u, 1 - v) to the slot's own (no -0),
    and the slots whose use reads another uv set than the stored one (left as the
    identity)."""
    out = np.tile(np.eye(3)[:2], (4, 1, 1))
    stored = use_matrix(stored_use(material))
    if abs(np.linalg.det(stored[:2, :2])) < 1e-12:
        return out, []
    back = np.linalg.inv(stored)
    other = []
    for slot, use in slot_uses(material, kind).items():
        if use is None:
            continue
        if int(use.uv) != uv_set(material):
            other.append(slot)
            continue
        out[slot] = (FLIP @ use_matrix(use) @ back @ FLIP)[:2]
    return out + 0.0, other
