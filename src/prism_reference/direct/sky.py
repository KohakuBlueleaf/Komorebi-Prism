"""The environment: the sun and the sky of an HDR map, the sky's spherical harmonics,
the octahedral map and the background a pixel sees."""

import numpy as np

from prism_reference.io.hdr import read_hdr
from prism_reference.raster.setup import grid
from prism_reference.scene.frame import TILE

F = np.float32
# Sun: the cone (degrees) around the brightest texel and the outer edge of its ring.
SUN_CONE_DEG = 4.0
SUN_RING_DEG = 8.0
LUMINANCE = np.array([0.2126, 0.7152, 0.0722])
# Spherical harmonics: the basis constants (bands 0 to 2) and the irradiance constants.
SH_Y = (0.282095, 0.488603, 1.092548, 0.315392, 0.546274)
C1, C2, C3, C4, C5 = (F(c) for c in (0.429043, 0.511664, 0.743125, 0.886227, 0.247708))
OCTA_SIDE = 2048  # the background's octahedral map, side in texels (`sky_side`)


def turned(d, turn_deg):
    """Directions (..., 3) turned about the y axis by turn_deg degrees (float64)."""
    a = np.radians(turn_deg)
    x, z = d[..., 0], d[..., 2]
    return np.stack(
        [np.cos(a) * x + np.sin(a) * z, d[..., 1], -np.sin(a) * x + np.cos(a) * z], -1
    )


def texel_directions(height, width):
    """Unit directions (H, W, 3) of the equirectangular map's texel centres and their
    solid angles (H, W), float64."""
    azimuth = 2 * np.pi * ((np.arange(width) + 0.5) / width - 0.5)
    elevation = np.pi * (0.5 - (np.arange(height) + 0.5) / height)
    a, e = np.meshgrid(azimuth, elevation)
    d = np.stack([-np.cos(a) * np.cos(e), np.sin(e), -np.sin(a) * np.cos(e)], -1)
    solid = (2 * np.pi / width) * (np.pi / height) * np.cos(e)
    return d, solid


def map_texel(d, height, width):
    """Row and column of the texel nearest to world directions d (n, 3) float32."""
    a = np.arctan2(-d[:, 2], -d[:, 0])
    e = np.arctan2(d[:, 1], np.sqrt(d[:, 0] * d[:, 0] + d[:, 2] * d[:, 2]))
    x = np.floor((a / F(2 * np.pi) + F(0.5)) * F(width)).astype(np.int64) % width
    y = np.floor((F(0.5) - e / F(np.pi)) * F(height)).astype(np.int64)
    return np.clip(y, 0, height - 1), x


def octahedral_texel(d, side):
    """Row and column of the texel of an octahedral map (side x side, y up) nearest
    to directions d (n, 3) float32 (folded below y = 0; sign 0 is +)."""
    norm = (np.abs(d[:, 0]) + np.abs(d[:, 1])) + np.abs(d[:, 2])
    u, v = d[:, 0] / norm, d[:, 2] / norm
    su = np.where(u < 0, F(-1), F(1))
    sv = np.where(v < 0, F(-1), F(1))
    below = d[:, 1] < 0
    u, v = (
        np.where(below, (F(1) - np.abs(v)) * su, u),
        np.where(below, (F(1) - np.abs(u)) * sv, v),
    )
    column = np.floor((u + F(1)) * F(0.5) * F(side)).astype(np.int64)
    row = np.floor((v + F(1)) * F(0.5) * F(side)).astype(np.int64)
    return np.clip(row, 0, side - 1), np.clip(column, 0, side - 1)


def octahedral_direction(u, v):
    """Unit directions (..., 3) float64 of octahedral coordinates u, v in [-1, 1]
    (unfolded where y = 1 - |u| - |v| < 0)."""
    u, v = np.asarray(u, np.float64), np.asarray(v, np.float64)
    y = 1 - np.abs(u) - np.abs(v)
    su, sv = np.where(u < 0, -1.0, 1.0), np.where(v < 0, -1.0, 1.0)
    u, v = (
        np.where(y < 0, (1 - np.abs(v)) * su, u),
        np.where(y < 0, (1 - np.abs(u)) * sv, v),
    )
    d = np.stack([u, y, v], -1)
    return d / np.linalg.norm(d, axis=-1, keepdims=True)


def octahedral_map(radiance, turn, side=OCTA_SIDE):
    """The map's radiance (side, side, 3) float32 resampled to an octahedral map of
    world directions (texel centres; nearest texel of the map turned by turn)."""
    c = (np.arange(side) + 0.5) / side * 2 - 1
    v, u = np.meshgrid(c, c, indexing="ij")
    d = turned(octahedral_direction(u, v).reshape(-1, 3), -turn).astype(np.float32)
    row, column = map_texel(d, radiance.shape[0], radiance.shape[1])
    return radiance[row, column].reshape(side, side, 3).astype(np.float32)


def sh_basis(d):
    """The 9 real spherical harmonics (..., 9) at unit directions d (..., 3): L00,
    L1-1 (y), L10 (z), L11 (x), L2-2 (xy), L2-1 (yz), L20, L21 (xz), L22."""
    x, y, z = d[..., 0], d[..., 1], d[..., 2]
    a, b, c, e, g = SH_Y
    return np.stack(
        [a + 0 * x, b * y, b * z, b * x, c * x * y, c * y * z, e * (3 * z * z - 1)]
        + [c * x * z, g * (x * x - y * y)],
        -1,
    )


def sh_turned(sh, turn_deg):
    """Coefficients sh (9, C) of a sky turned about y by turn_deg degrees: M sh, M the
    least-squares fit of the basis at turned directions, float64 on 128 directions."""
    d = texel_directions(8, 16)[0].reshape(-1, 3)
    m = np.linalg.lstsq(sh_basis(d), sh_basis(turned(d, turn_deg)), rcond=None)[0]
    return (m.T @ np.asarray(sh, np.float64)).astype(np.float32)


def sky_irradiance(sh, n):
    """Irradiance (n, 3) float32 of the sky with coefficients sh (9, 3) on unit
    normals n (n, 3): the quadratic form of Ramamoorthi and Hanrahan, in this order."""
    s = sh.astype(np.float32)
    x, y, z = n[:, 0:1], n[:, 1:2], n[:, 2:3]
    e = C4 * s[0] - C5 * s[6]
    e = e + C3 * s[6] * (z * z)
    e = e + C1 * s[8] * (x * x - y * y)
    e = e + F(2) * C1 * ((s[4] * (x * y) + s[7] * (x * z)) + s[5] * (y * z))
    e = e + F(2) * C2 * ((s[3] * x + s[1] * y) + s[2] * z)
    return e


def environment(path, turn):
    """The sun and the sky of a map turned by `turn` degrees about y: the sun's unit
    direction and colour, the sky's sh (9, 3) without the sun's cone, and the map."""
    radiance = read_hdr(path).astype(np.float64)
    height, width = radiance.shape[:2]
    d, solid = texel_directions(height, width)
    d = turned(d, turn)
    lum = radiance @ LUMINANCE
    peak = d[np.unravel_index(np.argmax(lum), lum.shape)]
    angle = np.degrees(np.arccos(np.clip(d @ peak, -1.0, 1.0)))
    cone, ring = angle < SUN_CONE_DEG, (angle >= SUN_CONE_DEG) & (angle < SUN_RING_DEG)
    around = (radiance[ring] * solid[ring, None]).sum(0) / solid[ring].sum()
    excess = np.maximum(radiance[cone] - around, 0.0) * solid[cone, None]
    weight = excess @ LUMINANCE
    direction = (d[cone] * weight[:, None]).sum(0)
    direction /= np.linalg.norm(direction)
    colour = excess.sum(0) / (excess.sum(0) @ LUMINANCE)
    sky = radiance.copy()
    sky[cone] = around
    sh = np.einsum("hwk,hwc,hw->kc", sh_basis(d), sky, solid)
    return {
        "sun_direction": direction.astype(np.float32),
        "sun_colour": colour.astype(np.float32),
        "sh": sh.astype(np.float32),
        "environment": radiance.astype(np.float32),
        "sun_share": float(weight.sum() / ((lum * solid).sum())),
    }


def environment_radiance(lights, d):
    """The environment's radiance (n, 3) along directions d (n, 3) turned by -turn
    about y: the nearest texel of the octahedral map (the map's frame, y up)."""
    angle = np.radians(-float(lights["turn"]))
    c, s = F(np.cos(angle)), F(np.sin(angle))
    x, z = d[:, 0], d[:, 2]
    d = np.stack([c * x + s * z, d[:, 1], c * z - s * x], -1)
    octa = lights["octahedral"]
    row, column = octahedral_texel(d, octa.shape[0])
    return octa[row, column]


def background(scene, lights):
    """The environment's radiance (H, W, 3) in each pixel's view direction
    (environment_radiance), over the padded frame (setup.grid)."""
    cam = scene["camera"]
    across, down = grid(scene)
    height, width = TILE * down, TILE * across
    ys, xs = np.mgrid[0:height, 0:width]
    sx = (xs.ravel().astype(np.float32) + F(0.5) - cam[13]) / cam[12]
    sy = (ys.ravel().astype(np.float32) + F(0.5) - cam[14]) / cam[12]
    d = (cam[9:12] + cam[3:6] * sx[:, None]) - cam[6:9] * sy[:, None]
    return environment_radiance(lights, d).reshape(height, width, 3)
