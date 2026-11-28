"""The sun as the card renders it: the scene's box, the lights at a moved sun, the sun's
path, a camera a quadrant of the shadow map, the sun region's words, the list entries a
sun view makes, and the shadow map from its pages."""

import numpy as np

from prism.stages.direct.light.model.numbers import (
    F32,
    LH,
    PAGE,
    RF_SUN_ACROSS_AT,
    RF_SUN_BYTES,
    RF_SUN_CAMERA_BYTES,
    RF_SUN_TABLE_AT,
    SHADE,
    SUN_PATH_HIGH,
    SUN_PATH_LOW,
    SUN_PATH_STEP,
)
from prism.stages.direct.light.model.table import light_table
from prism_common.mesh import kept
from prism_reference.direct.frame import TERMS
from prism_reference.direct.lights import shadow_side, sun_angles, sun_direction
from prism_reference.direct.shadow import (
    FILL_SIDE,
    SHADOW_SIDE,
    quadrant_camera,
    sun_camera,
)
from prism_reference.direct.sky import sh_turned
from prism_reference.raster.setup import camera_space, to_screen
from prism_reference.scene.frame import HEIGHT, TILE, WIDTH

BOX_VERSION = 1  # of a kept scene box


def scene_box(scene):
    """The scene's box as a scene of two points (its least and greatest corner): what
    sun_camera and shadow_map's texel read of the positions."""
    positions = scene["positions"]
    corners = kept(
        positions,
        scene["indices"],
        "box",
        BOX_VERSION,
        lambda: np.stack([positions.min(0), positions.max(0)]),
    )
    return {"positions": corners}


def sun_lights(lights, scene, azimuth, elevation):
    """The reference's moved lights from the loaded `lights` without its shadow map:
    turn, sh_turned, direction, sun_camera at the map's side, texel, bias; elevation
    <= 0: irradiance 0. The shadow map stays the loaded array; `scene` may be
    scene_box's."""
    own_azimuth, _ = sun_angles(lights["sun_direction"])
    change = float(azimuth) - own_azimuth
    sun = sun_direction(azimuth, elevation)
    out = dict(lights)
    out["turn"] = np.float32(float(lights["turn"]) + change)
    out["sh"] = sh_turned(lights["sh"], change)
    out["sun_direction"] = sun
    distance = float(lights["shadow_texel"] * lights["shadow_camera"][12])
    texels = float(lights["shadow_bias"]) * distance**2 / float(lights["shadow_texel"])
    positions = scene["positions"]
    camera = sun_camera(positions, sun, shadow_side(lights))
    out["shadow_camera"] = camera
    if elevation <= 0:
        out["sun_irradiance"] = np.zeros(3, dtype=np.float32)
        return out
    centre = (positions.min(0) + positions.max(0)) / 2
    texel = F32(np.linalg.norm(camera[0:3].astype(np.float64) - centre) / camera[12])
    out["shadow_texel"] = texel
    distance = float(texel * camera[12])
    out["shadow_bias"] = F32(texels * float(texel) / distance**2)
    return out


def sun_path(azimuth, step):
    """The sun at `step` of its path: the azimuth from `azimuth` on, SUN_PATH_STEP
    degrees a step; the elevation SUN_PATH_LOW to SUN_PATH_HIGH, a sine over 24 steps.
    """
    middle = (SUN_PATH_LOW + SUN_PATH_HIGH) / 2
    swing = (SUN_PATH_HIGH - SUN_PATH_LOW) / 2
    angle = np.radians(SUN_PATH_STEP * step)
    return float(azimuth + SUN_PATH_STEP * step), float(middle + swing * np.sin(angle))


def quadrant_cameras(camera, side):
    """The sun's cameras of a shadow map of `side` from its camera: (side / 1,024)^2
    quadrant_camera, quadrant (i, j) the (j n + i)-th; ValueError for a side that is
    not whole quadrants."""
    across = side // FILL_SIDE
    if side % FILL_SIDE or across < 1:
        raise ValueError(f"a shadow map of side {side}: whole quadrants of {FILL_SIDE}")
    return [quadrant_camera(camera, i, j) for j in range(across) for i in range(across)]


def sun_region(lights, materials, terms=TERMS, field=None, indirect=True):
    """The frame thread's sun region: the sun's camera of each quadrant of the shadow
    map as COUNT's and SETUP's camera page, the quadrants a side, then LIGHT's table
    (light_table; `field` with the term indirect, `indirect` its switch); ValueError
    when the cameras pass the quadrants' word."""
    words = np.zeros(RF_SUN_BYTES // 4, dtype=np.uint32)
    side = shadow_side(lights)
    cameras = quadrant_cameras(lights["shadow_camera"], side)
    step = RF_SUN_CAMERA_BYTES // 4
    if len(cameras) * RF_SUN_CAMERA_BYTES > RF_SUN_ACROSS_AT:
        raise ValueError(
            f"a shadow map of side {side}: {len(cameras)} cameras of "
            f"{RF_SUN_CAMERA_BYTES} B pass the region's {RF_SUN_ACROSS_AT} B before "
            "its quadrants' word"
        )
    for quadrant, camera in enumerate(cameras):
        words[step * quadrant : step * quadrant + SHADE["kCamWordsShade"]] = (
            camera.view(np.uint32)
        )
    words[RF_SUN_ACROSS_AT // 4] = side // FILL_SIDE
    at = RF_SUN_TABLE_AT // 4
    words[at : at + LH["kLightTableBytes"] // 4] = light_table(
        lights, materials, terms, field, indirect
    )
    return words


def sun_entries(scene, keeps, suns, side=SHADOW_SIDE):
    """The most list entries each layer (each mask of `keeps`) makes in one of the sun's
    views (a quadrant of a shadow map of `side`) over `suns` ((azimuth, elevation)):
    setup's box, the binning's tiles, zero areas counted too. A number a mask."""
    box = scene_box(scene)
    most = [0] * len(keeps)
    half, tile = F32(0.5), TILE
    corners = [np.ascontiguousarray(scene["indices"][:, k]) for k in range(3)]

    def lowest(values):
        return np.minimum(
            np.minimum(values[corners[0]], values[corners[1]]), values[corners[2]]
        )

    def highest(values):
        return np.maximum(
            np.maximum(values[corners[0]], values[corners[1]]), values[corners[2]]
        )

    for azimuth, elevation in suns:
        sun = sun_direction(azimuth, elevation)
        view = sun_camera(box["positions"], sun, side)
        for camera in quadrant_cameras(view, side):
            xc, yc, zc = camera_space({**scene, "camera": camera})
            x, y, _ = to_screen(camera, xc, yc, zc)
            x0 = np.clip(np.ceil(lowest(x) - half), 0, WIDTH)
            x1 = np.clip(np.floor(highest(x) - half), -1, WIDTH - 1)
            y0 = np.clip(np.ceil(lowest(y) - half), 0, HEIGHT)
            y1 = np.clip(np.floor(highest(y) - half), -1, HEIGHT - 1)
            tiles = np.where(
                (x0 <= x1) & (y0 <= y1),
                (x1 // tile - x0 // tile + 1) * (y1 // tile - y0 // tile + 1),
                0,
            )
            for index, keep in enumerate(keeps):
                most[index] = max(most[index], int(tiles[keep].sum()))
    return most


def shadow_of_pages(pages):
    """The shadow map (side, side) float32 from its light pages (map_pages' layout)."""
    pages = np.asarray(pages, dtype=np.uint32)
    across = round(np.sqrt(len(pages)))
    blocks = pages.reshape(across, across, PAGE, PAGE).transpose(0, 2, 1, 3)
    return np.ascontiguousarray(blocks.reshape(across * PAGE, across * PAGE)).view(F32)
