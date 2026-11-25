"""The sky for the elements: 25 spherical harmonics, the map without its sun, the fit of
its coefficients and each element's transfer row."""

import numpy as np

from prism_reference.direct.sky import (
    SUN_CONE_DEG,
    SUN_RING_DEG,
    environment_radiance,
    octahedral_direction,
    texel_directions,
)
from prism_reference.direct.sky import sh_basis as sh_basis_9
from prism_reference.indirect.elements import cosine_directions
from prism_reference.trace.batch import trace
from prism_reference.trace.tracer import TMAX

F = np.float32
LUMINANCE = np.array([0.2126, 0.7152, 0.0722])
# Rays a transfer row and their seed; bands 0 to 4, fitted on SKY_GRID x 2 SKY_GRID.
SKY_RAYS, SKY_SEED = 256, 51
SKY_TERMS = 25
SKY_GRID = 256
_MAPS = {}


def sh_basis(d):
    """The 25 real spherical harmonics of bands 0 to 4 (..., 25) at unit directions d
    (..., 3), float64; the first 9 are the direct light's (z the polar axis)."""
    d = np.asarray(d, np.float64)
    x, y, z = d[..., 0], d[..., 1], d[..., 2]
    x2, y2, z2 = x * x, y * y, z * z
    band3 = [0.590044 * y * (3 * x2 - y2), 2.890611 * x * y * z]
    band3 += [0.457046 * y * (5 * z2 - 1), 0.373176 * z * (5 * z2 - 3)]
    band3 += [0.457046 * x * (5 * z2 - 1), 1.445306 * z * (x2 - y2)]
    band3 += [0.590044 * x * (x2 - 3 * y2)]
    band4 = [2.503343 * x * y * (x2 - y2), 1.770131 * y * z * (3 * x2 - y2)]
    band4 += [0.946175 * x * y * (7 * z2 - 1), 0.669047 * y * z * (7 * z2 - 3)]
    band4 += [0.105786 * (35 * z2 * z2 - 30 * z2 + 3), 0.669047 * x * z * (7 * z2 - 3)]
    band4 += [0.473087 * (x2 - y2) * (7 * z2 - 1), 1.770131 * x * z * (x2 - 3 * y2)]
    band4 += [0.625836 * (x2 * (x2 - 3 * y2) - y2 * (3 * x2 - y2))]
    return np.concatenate([sh_basis_9(d), np.stack(band3 + band4, -1)], -1)


def sky_map(lights):
    """The octahedral map with its sun removed as the sky's coefficients have it (the
    cone takes the ring's mean). Kept per map."""
    octa = lights["octahedral"]
    key = ("sky", id(octa))
    if key in _MAPS and _MAPS[key][0] is octa:
        return _MAPS[key][1]
    side = octa.shape[0]
    c = (np.arange(side) + 0.5) / side * 2 - 1
    v, u = np.meshgrid(c, c, indexing="ij")
    d = octahedral_direction(u, v)
    peak = d.reshape(-1, 3)[np.argmax(octa.reshape(-1, 3) @ LUMINANCE)]
    angle = np.degrees(np.arccos(np.clip(d @ peak, -1.0, 1.0)))
    cone = angle < SUN_CONE_DEG
    ring = (angle >= SUN_CONE_DEG) & (angle < SUN_RING_DEG)
    clean = octa.astype(F).copy()
    clean[cone] = octa[ring].mean(0)
    _MAPS[key] = (octa, clean)
    return clean


def sky_radiance(lights, d):
    """The sky's radiance (n, 3) along world directions d (n, 3): the nearest texel of
    `sky_map`, d turned by -turn about y (as `environment_radiance`)."""
    return environment_radiance({**lights, "octahedral": sky_map(lights)}, d)


def sky_coefficients(lights):
    """The sky's 25 coefficients (SKY_TERMS, 3) float32: the least-squares fit of
    `sh_basis` to `sky_radiance`, weighted by solid angle, on an equirectangular grid.
    """
    d, solid = texel_directions(SKY_GRID, 2 * SKY_GRID)
    d, root = d.reshape(-1, 3), np.sqrt(solid.ravel())[:, None]
    radiance = sky_radiance(lights, d.astype(F)).astype(np.float64)
    fit = np.linalg.lstsq(sh_basis(d) * root, radiance * root, rcond=None)[0]
    return fit.astype(F)


def transfer(tree, elements, eps, rays=SKY_RAYS):
    """Each element's transfer row (N, SKY_TERMS) float32: pi / rays x the sum of
    `sh_basis` over its escaping cosine rays from p + eps n (any hit)."""
    p, n = elements["position"], elements["normal"]
    out = np.zeros((len(p), SKY_TERMS))
    index = elements["sample"].astype(np.int64) * rays
    origin = p + n * F(eps)
    for k in range(rays):
        d = cosine_directions(index + k, n, SKY_SEED)
        _, tri, _, _ = trace(tree, origin, d, TMAX, any_hit=True)
        free = np.nonzero(tri < 0)[0]
        out[free] += sh_basis(d[free])
    return (out * (np.pi / rays)).astype(F)
