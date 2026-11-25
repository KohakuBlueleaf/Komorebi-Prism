"""The stages of the pipeline; each implementation is a self-contained package,
registered when it is imported here."""

from prism.stages import raster
from prism.stages.direct import light, shadow_pcf
from prism.stages.indirect import field_update, transport
from prism.stages.post import show

__all__ = ["field_update", "light", "raster", "shadow_pcf", "show", "transport"]
