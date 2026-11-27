"""The display of a described scene's linear colour: the sidecar's exposure, view
transform (its tables when given), look and gamma, with what is not applied named."""

import numpy as np

from prism_reference.post.display import to_srgb_standard8
from prism_reference.post.view import view8

TRANSFORMS = ("Standard",)  # the view transforms this code has
NO_LOOK = ("", "None")


def displayed(colour, render, view=None):
    """Display bytes (H, W, 3) of linear colour under `render` (a description Render,
    or None): x 2^exposure, the transform, then a 1 / gamma power; and the notes.
    `view`: (operations, notes) of `post.view.view_of`, the transform's tables."""
    exposure = float(render.exposure) if render is not None else 0.0
    transform = render.view_transform if render is not None else "Standard"
    look = render.look if render is not None else ""
    gamma = float(render.gamma) if render is not None else 1.0
    ops, notes = view if view is not None else (None, [])
    notes = list(notes)
    if view is None and transform not in TRANSFORMS:
        notes.append(f"view transform {transform!r}: the standard sRGB transfer used")
    if view is None and look not in NO_LOOK:
        notes.append(f"look {look!r}: not applied")
    x = np.asarray(colour, np.float64) * 2.0**exposure
    picture = to_srgb_standard8(x) if ops is None else view8(ops, x)
    if gamma != 1.0 and gamma > 0:
        scaled = (picture.astype(np.float64) / 255.0) ** (1.0 / gamma)
        picture = np.rint(scaled * 255).astype(np.uint8)
    return picture, notes
