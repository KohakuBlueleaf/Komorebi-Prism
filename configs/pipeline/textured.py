"""The preset `textured`: visibility, then each layer's colour from its materials
(SHADE), then the frame converted for display on the card and pushed to the host; a
frame a FRAME command to the thread."""

from prism import stages  # noqa: F401  (registers the implementations)
from prism.core.pipeline import Pipeline
from prism.stages.material.texture.check.thread_frame import reference_picture
from prism.stages.post.show.check import shaded

PIPELINE = Pipeline(
    "textured",
    ["raster", "material.texture", "post.show"],
    inputs=("scene.mesh", "view.camera"),
)
OPTIONS = {"frames": 16, "balance": True, "recount": False, "push": True}
# the options a runner takes from the scene's files: its materials
SCENE_INPUTS = ("materials",)


def reference(loop, scene):
    """The picture a frame of `scene` (a view at its size) is compared with: its shaded
    frame on the loop's materials."""
    return reference_picture(scene, loop.options["materials"])


# the picture a frame's is compared with, and the judge of a frame's picture (the
# numbers of measurements/textured_show), each of (loop, scene)
REFERENCE = reference
JUDGE = shaded
