"""The preset `raster`: visibility, then the frame converted for display on the card and
pushed to the host; a frame a FRAME command to the thread."""

from prism import stages  # noqa: F401  (registers the implementations)
from prism.core.pipeline import Pipeline
from prism.stages.post.show.check import reference_display, vertex_colour

PIPELINE = Pipeline(
    "raster", ["raster", "post.show"], inputs=("scene.mesh", "view.camera")
)
OPTIONS = {"frames": 64, "balance": True, "recount": False, "push": True}


def reference(loop, scene):
    """The picture a frame of `scene` (a view at its size) is compared with: its vertex
    colour for display."""
    return reference_display(scene)


# the picture a frame's is compared with, and the judge of a frame's picture (the
# numbers of measurements/raster_show), each of (loop, scene)
REFERENCE = reference
JUDGE = vertex_colour
