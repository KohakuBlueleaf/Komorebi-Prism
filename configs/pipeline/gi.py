"""The preset `gi`: the lit frame (`lit`'s implementations, the same frame commands)
lit with the indirect field; after the sun moves, the sun's pass, then the field's update
on the card (`field`'s implementations), each a thread command before the next frame."""

from prism import stages  # noqa: F401  (registers the implementations)
from prism.core.compute import FRAME_COMPUTE
from prism.core.pipeline import Pipeline
from prism.stages.direct.light.check.thread_frame import lit, reference
from prism_reference.direct.frame import TERMS

PIPELINE = Pipeline(
    "gi",
    [
        "raster",
        "material.texture",
        "direct.shadow_pcf",
        "indirect.transport",
        "indirect.field_update",
        "direct.light",
        "post.show",
    ],
    inputs=("scene.mesh", "view.camera", "elements.radiance"),
)
OPTIONS = {
    "frames": 16,
    "balance": True,
    "recount": False,
    "push": True,
    "terms": (*TERMS, "indirect"),
    "bounces": 2,
    "compute": FRAME_COMPUTE,  # the program's: Apply joins the frame's classes with it
}
# the options a runner takes from the scene's files: its materials, its name (also the
# field's scene and its transport set), its lights
SCENE_INPUTS = ("materials", "name", "lights")
# the scene's files it reads beside the mesh (scene.public.files): the lights' and
# the field's, and the transport set
SCENE_FILES = ("materials", "lighting", "indirect", "transport")
# the picture a frame's is compared with (the lit frame with the field) and the judge of
# a frame's picture, each of (loop, scene)
REFERENCE = reference
JUDGE = lit
