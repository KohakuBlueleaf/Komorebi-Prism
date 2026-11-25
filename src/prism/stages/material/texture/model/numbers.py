"""The texture stage's numbers: SHADE's header constants, the shared surface and texel
pages' ones, and the texture page's sizes."""

from pathlib import Path

import numpy as np

from prism.core.headers import INCLUDE, constexpr
from prism_reference.material.kinds import ALBEDO, NORMAL, SPECULAR

STAGE = Path(__file__).resolve().parent.parent
KERNELS = STAGE / "kernels"
SH = constexpr(KERNELS / "shade.h")  # SHADE's alone
SURFACE = constexpr(INCLUDE / "surface.h")  # the layouts SHADE and LIGHT read
PAGES = constexpr(INCLUDE / "texel_pages" / "protocol.h")  # the texel pages' sizes
PAGE = 32  # a texture page: 32 x 32 texels of one level
KEY_PAGES = (1 << 20) - 1  # the most pages a texel's key holds
F32 = np.float32
LEVEL_SLOTS = (ALBEDO, NORMAL, SPECULAR)  # the record's levels
