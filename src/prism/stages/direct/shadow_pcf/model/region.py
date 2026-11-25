"""The sun region as the unit's header lays it out: LIGHT's table, then the sun's words
and a camera a quadrant; the lights at a sun; the times region's rows."""

from pathlib import Path

import numpy as np

from prism.core.headers import defined
from prism.core.resources import DIRECTOR_NUMBERS, LINE, lines
from prism.stages.direct.light.model.numbers import LH, PAGE
from prism.stages.direct.light.model.sun import quadrant_cameras as sun_quadrants
from prism.stages.direct.light.model.sun import sun_lights
from prism_reference.direct.lights import shadow_side
from prism_reference.direct.shadow import FILL_SIDE
from prism_reference.scene.frame import frame_grid

THREAD = Path(__file__).resolve().parents[1] / "thread"
H = defined(THREAD / "direct_shadow_pcf_unit.h")
CAMERA_WORDS = dict(DIRECTOR_NUMBERS)["camera"]  # a view's camera: the director's
SUN_AT = -(-LH["kLightTableBytes"] // LINE) * LINE  # the sun's words after the table
QUADRANT = (FILL_SIDE, FILL_SIDE)  # a quadrant's frame: one fill of the grid


def across_of(lights):
    """The quadrants a row of the lights' shadow map; ValueError for a side that is
    not whole quadrants."""
    side = shadow_side(lights)
    if side % FILL_SIDE or side < FILL_SIDE:
        raise ValueError(f"a shadow map of side {side}: whole quadrants of {FILL_SIDE}")
    return side // FILL_SIDE


def quadrant_cameras(lights):
    """The sun's camera of each quadrant of the lights' shadow map (the light model's,
    at its side)."""
    return sun_quadrants(lights["shadow_camera"], shadow_side(lights))


def lights_at(lights, box, sun):
    """`lights` with the sun at `sun` (azimuth, elevation; None: their own), `box` the
    scene's (scene_box)."""
    return lights if sun is None else sun_lights(lights, box, *sun)


def region_bytes(quadrants):
    """The sun region's bytes for `quadrants` cameras."""
    return SUN_AT + 4 * lines(H["SHADOW_PCF_CAMERAS"] + quadrants * CAMERA_WORDS)


def region_words(lights, grid, target, first=0):
    """The sun region's words: LIGHT's table's 0 (another host's), then the
    quadrants, a side, the quadrant's `grid` word and its tiles, the map's tensor
    `target` (from page `first`), then each quadrant's camera of `lights`."""
    cameras = quadrant_cameras(lights)
    words = np.zeros(region_bytes(len(cameras)) // 4, dtype=np.uint32)
    sun = words[SUN_AT // 4 :]
    across, down = frame_grid(QUADRANT)
    places = {
        "QUADRANTS": len(cameras),
        "ACROSS": across_of(lights),
        "GRID": grid,
        "TILES": across * down,
        "TILES_ACROSS": across,
        "TILES_DOWN": down,
        "TARGET": target.address,
        "TARGET_FIRST": first,
        "TARGET_PAGES": target.pages,
    }
    for name, value in places.items():
        sun[H[f"SHADOW_PCF_{name}"]] = value
    for quadrant, camera in enumerate(cameras):
        at = H["SHADOW_PCF_CAMERAS"] + quadrant * CAMERA_WORDS
        sun[at : at + CAMERA_WORDS] = np.asarray(camera, np.float32).view(np.uint32)
    return words


def map_pages(lights):
    """The shadow map's pages: (side / PAGE)^2."""
    return (shadow_side(lights) // PAGE) ** 2


def times_bytes(quadrants):
    """The times region's bytes: SHADOW_PCF_TIMES_ROWS rows of the pass's words and a
    word a quadrant, on lines."""
    words = lines(H["SHADOW_PCF_T_QUADRANT"] + quadrants)
    return 4 * words * H["SHADOW_PCF_TIMES_ROWS"]


def times_rows(raw, quadrants, served, microseconds):
    """The SUN commands' rows (the last SHADOW_PCF_TIMES_ROWS of `served`) of the times
    region's bytes `raw`: number, code, the pass and each quadrant in microseconds."""
    rows = H["SHADOW_PCF_TIMES_ROWS"]
    words = np.frombuffer(raw, np.uint32).reshape(rows, -1)
    out = []
    for number in range(max(0, served - rows), served):
        row = words[number % rows]
        first = H["SHADOW_PCF_T_QUADRANT"]
        out.append(
            {
                "number": int(row[H["SHADOW_PCF_T_NUMBER"]]),
                "code": int(row[H["SHADOW_PCF_T_CODE"]]),
                "pass": float(row[H["SHADOW_PCF_T_PASS"]]) * microseconds,
                "quadrants": [
                    float(t) * microseconds for t in row[first : first + quadrants]
                ],
            }
        )
    return out
