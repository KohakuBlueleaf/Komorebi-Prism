"""The tile threads of the threads' presets, each the steps it runs in order and the
planes they share: textured (visibility, material, post), lit (visibility, the lit
material, light, post; a DEPTH view its steps marked depth, then depth out), gi with
the one-tile product's step before the light."""

from prism.core.thread.module import TileThread
from prism.stages.direct.light.steps.step import LIGHT, LIGHT_NEAR
from prism.stages.indirect.near_tile.steps.step import NEAR_LIGHT, NEAR_TILE
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

# GI with the one-tile product (the option near_tile): its step before the light's
GI_NEAR = TileThread(
    steps=(VISIBILITY, LIT_STEP, NEAR_TILE, LIGHT_NEAR, POST, DEPTH_OUT),
    planes=(VISIBILITY_PLANE, SURFACE_PLANE, NEAR_LIGHT),
)
