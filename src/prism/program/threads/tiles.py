"""The tile threads of the threads' presets, each the steps it runs in order and the
planes they share: textured (visibility, material, post), lit (visibility, the lit
material, light, post; a DEPTH view its steps marked depth, then depth out)."""

from prism.core.thread.module import TileThread
from prism.stages.direct.light.steps.step import LIGHT
from prism.stages.material.texture.steps.step import LIT_STEP, STEP, SURFACE_PLANE
from prism.stages.post.show.steps.step import POST
from prism.stages.raster.steps.depth.step import DEPTH_OUT
from prism.stages.raster.steps.step import STEP as VISIBILITY
from prism.stages.raster.steps.step import VISIBILITY as VISIBILITY_PLANE

TEXTURED = TileThread(
    steps=(VISIBILITY, STEP, POST),
    planes=(VISIBILITY_PLANE,),
)

LIT = TileThread(
    steps=(VISIBILITY, LIT_STEP, LIGHT, POST, DEPTH_OUT),
    planes=(VISIBILITY_PLANE, SURFACE_PLANE),
)

GI = LIT  # the field's update is the job thread's; the tile thread is lit's
