"""Visibility: binning, setup and fill into the G-buffer."""

from prism.core.implementation import IMPLEMENTATIONS, Implementation
from prism.stages.raster.check.thread_frame import check
from prism.stages.raster.device import made
from prism.stages.raster.host import RasterHost
from prism.stages.raster.unit import UNIT

RASTER = IMPLEMENTATIONS.register(
    "raster",
    Implementation(
        name="raster",
        fills=("raster",),
        reads=("scene.mesh", "view.camera"),
        writes=("frame.visibility", "frame.lists"),
        device=made,
        host=RasterHost,
        check=check,
        thread=UNIT,
    ),
)
