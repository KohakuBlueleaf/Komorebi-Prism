"""The preset `lit`: visibility, each layer's surface from its materials (SHADE), the
sun's shadow map when the sun moves (a thread command of its own, no frame work), the
direct light with the tone step, then the frame converted for display on the card and
pushed to the host; a frame a FRAME command to the thread."""

from prism import stages  # noqa: F401  (registers the implementations)
from prism.core.pipeline import Pipeline
from prism.stages.direct.light.check.thread_frame import lit, reference

PIPELINE = Pipeline(
    "lit",
    ["raster", "material.texture", "direct.shadow_pcf", "direct.light", "post.show"],
    inputs=("scene.mesh", "view.camera"),
)
OPTIONS = {"frames": 16, "balance": True, "recount": False, "push": True}
# the options a runner takes from the scene's files: its materials, its name, its lights
# (the texture stage's lit surfaces, the sun's and LIGHT's)
SCENE_INPUTS = ("materials", "name", "lights")
# the scene's files it reads beside the mesh (scene.public.files)
SCENE_FILES = ("materials", "lighting")

# the picture a frame's is compared with, and the judge of a frame's picture (the
# numbers of measurements/lit_frame), each of (loop, scene)
REFERENCE = reference
JUDGE = lit
