"""LIGHT's numbers: its terms, a light page, the sun's path, and the places of the frame
thread's sun region."""

from pathlib import Path

import numpy as np

from prism.core.headers import INCLUDE, constexpr

STAGE = Path(__file__).resolve().parent.parent
KERNELS = STAGE / "kernels"
LH = constexpr(KERNELS / "light.h")  # LIGHT's table, terms, items, profile
SURFACE = constexpr(INCLUDE / "surface.h")  # the lit frame's planes
TEXEL_PAGES = constexpr(INCLUDE / "texel_pages" / "protocol.h")  # slots, asks, done
# SHADE's table, its kinds and the camera's words
SHADE = constexpr(STAGE.parents[1] / "material" / "texture" / "kernels" / "shade.h")

F32 = np.float32
RSQRT_MAGIC = 0x5F3759DF  # 1 / sqrt(x) estimate from the bits, then Newton steps
SURFACE_NAMES = ("a", "normal", "visibility", "specular")
# the card's terms past the ones always on, by the reference's names: light.h kTerm*
BASE_TERMS = ("sky", "ambient", "sun")
CARD_TERMS = {
    "shadow": "kTermShadow",
    "lamps": "kTermLamps",
    "specular": "kTermSpecular",
    "background": "kTermBackground",
    "indirect": "kTermIndirect",
}
PAGE = 32  # a light page: 32 x 32 values of a map
SUN_PATH_STEP = 15.0  # degrees of azimuth a step of the sun's path
SUN_PATH_LOW, SUN_PATH_HIGH = 25.0, 80.0  # its elevation's range
# the sun region: a camera page a quadrant, the quadrants a side, then LIGHT's table
RF_SUN_CAMERA_BYTES = 64
RF_SUN_ACROSS_AT = 256
RF_SUN_TABLE_AT = 4096
RF_SUN_BYTES = 8192
