"""The shaded frame's check: the card's 8-bit image against the reference's shaded
picture, later pieces of cut triangles counted apart."""

import numpy as np

from prism.stages.material.texture.model.layers import as_shaded, later_pieces
from prism_reference.material.kinds import (
    EMISSIVE,
    FLAT,
    LIT,
    MASKED,
    TEXTURED,
    TRANSPARENT,
)
from prism_reference.raster.frames import picture, rasterize_shaded


def check(view, materials, got, to_srgb8):
    """The card's 8-bit image `got` (H, W, >= 3) against the reference's shaded picture
    of `view` on as_shaded(materials): pixels over 2 apart in a channel, shares over
    those not on later_pieces and over the frame. Returns (report, compared, true)."""

    def crop(image):
        return picture(image, view)

    shaded = rasterize_shaded(view, as_shaded(materials))
    want = to_srgb8(crop(shaded["colour"]))
    true = to_srgb8(crop(rasterize_shaded(view, materials)["colour"]))
    error = np.abs(got[..., :3].astype(np.int16) - want.astype(np.int16)).max(axis=2)
    over = error > 2
    tri = shaded["tri"]
    apart = crop(later_pieces(view, materials, tri))
    tri = crop(tri)
    kind = np.where(tri >= 0, materials["kind"][materials["material"]][tri], -1)
    names = {-1: "background", FLAT: "flat", TEXTURED: "textured"}
    names.update({MASKED: "masked", LIT: "lit", EMISSIVE: "emissive"})
    checked = ~apart
    # the glass in front: a kind of its own, its later pieces apart too
    front = shaded["front"]
    glass_apart = np.zeros_like(crop(front))
    if front.any():
        glass_tri = np.where(front, shaded["glass"]["tri"], -1)
        glass_apart = crop(later_pieces(view, materials, glass_tri))
    front = crop(front)
    if front.any():
        kind = np.where(front, TRANSPARENT, kind)
        names[TRANSPARENT] = "glass_in_front"
        checked = checked & ~glass_apart
    report = {
        "checked": int(checked.sum()),
        "differ": int((over & checked).sum()),
        "share": round(float((over & checked).sum() / max(checked.sum(), 1)), 6),
        "max_error": int(error[checked].max(initial=0)),
        "later_pieces": int((apart | glass_apart).sum()),
        "later_pieces_differ": int((over & (apart | glass_apart)).sum()),
        "glass_in_front": int(front.sum()),
        "frame_differ": int(over.sum()),
        "frame_share": round(float(over.mean()), 6),
        "differ_by_kind": {
            name: int((over & checked & (kind == value)).sum())
            for value, name in names.items()
        },
        "share_by_kind": {
            name: round(
                float(
                    (over & checked & (kind == value)).sum()
                    / max((checked & (kind == value)).sum(), 1)
                ),
                6,
            )
            for value, name in names.items()
        },
    }
    return report, want, true
