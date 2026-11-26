"""The display of a described scene's linear colour: the sidecar's exposure, view
transform, look and gamma, with what the code does not have named."""

import numpy as np

from prism_reference.post.display import to_srgb_standard8

TRANSFORMS = ("Standard",)  # the view transforms this code has
NO_LOOK = ("", "None")


def displayed(colour, render):
    """Display bytes (H, W, 3) of linear colour under `render` (a description Render,
    or None): x 2^exposure, the transform, then a 1 / gamma power; and the notes."""
    exposure = float(render.exposure) if render is not None else 0.0
    transform = render.view_transform if render is not None else "Standard"
    look = render.look if render is not None else ""
    gamma = float(render.gamma) if render is not None else 1.0
    notes = []
    if transform not in TRANSFORMS:
        notes.append(f"view transform {transform!r}: the standard sRGB transfer used")
    if look not in NO_LOOK:
        notes.append(f"look {look!r}: not applied")
    x = np.asarray(colour, np.float64) * 2.0**exposure
    picture = to_srgb_standard8(x)
    if gamma != 1.0 and gamma > 0:
        scaled = (picture.astype(np.float64) / 255.0) ** (1.0 / gamma)
        picture = np.rint(scaled * 255).astype(np.uint8)
    return picture, notes
