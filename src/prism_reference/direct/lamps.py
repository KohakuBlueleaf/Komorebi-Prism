"""Lamps: the lamps found among the emissive triangles, the irradiance of one point
light and a lamp's shape (an axis and a falloff about it: a spot's cone, a cosine lobe,
none for a point)."""

import numpy as np

from prism_reference.material.kinds import ALBEDO, EMISSIVE
from prism_reference.material.texture import TEXEL_LINEAR
from prism_reference.raster.vector import dot3

F = np.float32
SHAPE_WORDS = 6  # a lamp's shape: axis (3), scale, offset, square
LEAST_CONE = 1e-3  # glTF's floor on cos(inner) - cos(outer)


def emission_colours(materials):
    """Per material its emission colour (M, 3): the base colour times its albedo
    texture's 1 x 1 level (linear) when it has one, scaled to a largest channel of 1."""
    colour = materials["base_colour"].astype(np.float32).copy()
    for m, tex in enumerate(materials["textures"][:, ALBEDO]):
        if tex >= 0:
            last = materials["levels"][tex] - 1
            start = materials["mip"][tex, last, 0]
            colour[m] *= TEXEL_LINEAR[materials["texels"][start : start + 3]]
    top = colour.max(axis=1, keepdims=True)
    return np.where(top > 0, colour / np.where(top > 0, top, F(1)), F(1))


def find_lamps(scene, materials, merge_distance, lamp_scale):
    """Point lights at the lamps: connected emissive triangles, groups nearer than
    merge_distance merged; at the area-weighted centroid, colour and lamp_scale x area.
    """
    kind = materials["kind"][materials["material"]]
    tris = np.nonzero(kind == EMISSIVE)[0]
    counts = {"emissive_triangles": len(tris), "groups": 0, "lamps": 0}
    empty = np.zeros((0, 3), dtype=np.float32)
    if len(tris) == 0:
        return empty, empty, np.zeros(0, dtype=np.float32), counts
    idx = scene["indices"][tris]
    label = np.arange(len(tris))
    while True:
        vertex = np.full(len(scene["positions"]), len(tris))
        for k in range(3):
            np.minimum.at(vertex, idx[:, k], label)
        new = vertex[idx].min(1)
        if np.array_equal(new, label):
            break
        label = new
    group = np.unique(label, return_inverse=True)[1]
    p = scene["positions"][idx].astype(np.float64)
    area = 0.5 * np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1)
    centre = p.mean(1)

    def weighted(values, by):
        total = np.zeros((by.max() + 1, values.shape[1]))
        np.add.at(total, by, values * area[:, None])
        mass = np.bincount(by, area, by.max() + 1)
        return total / np.maximum(mass, 1e-300)[:, None], mass

    centroid, _ = weighted(centre, group)
    counts["groups"] = len(centroid)
    merged = np.arange(len(centroid))
    for i in range(len(centroid)):
        near = np.nonzero(
            np.linalg.norm(centroid - centroid[i], axis=1) < merge_distance
        )[0]
        roots = np.unique(merged[near])
        merged[np.isin(merged, roots)] = roots.min()
    lamp = np.unique(merged, return_inverse=True)[1][group]
    position, mass = weighted(centre, lamp)
    colour, _ = weighted(emission_colours(materials)[materials["material"][tris]], lamp)
    counts["lamps"] = len(position)
    return (
        position.astype(np.float32),
        colour.astype(np.float32),
        (lamp_scale * mass).astype(np.float32),
        counts,
    )


def point_irradiance(intensity, size, radius, position, points, normals):
    """Irradiance (n,) float32 of one point light of intensity I at position:
    I max(0, n.l) / (d^2 + s^2) (1 - (d / r)^4)^2 inside r, exactly 0 from r on."""
    to = position[None, :] - points
    d2 = dot3(to, to)
    d = np.sqrt(d2)
    to_light = to / np.where(d > 0, d, F(1))[:, None]
    q = (d / F(radius)) * (d / F(radius))
    fall = (F(1) - q * q) * (F(1) - q * q)
    e = F(intensity) * np.maximum(dot3(normals, to_light), F(0)) / (d2 + F(size) ** 2)
    return np.where(d < F(radius), e * fall, F(0)), to_light


def lamp_shapes(lights):
    """The lamps' shapes (L, SHAPE_WORDS) float32: the lights' `lamp_shape`, else every
    lamp a point (zeros)."""
    if "lamp_shape" in lights:
        return np.asarray(lights["lamp_shape"], dtype=F).reshape(-1, SHAPE_WORDS)
    return np.zeros((len(lights["lamp_intensity"]), SHAPE_WORDS), dtype=F)


def is_area(shape):
    """Whether a lamp's shape is an area light's stand-in (a cosine lobe: a scale,
    offset and square 0)."""
    return shape[3] != 0 and shape[4] == 0 and shape[5] == 0


def without_areas(lights):
    """The lights without the area lights' stand-ins (their lamps left out)."""
    if "lamp_shape" not in lights:
        return lights
    kept = np.array([not is_area(s) for s in lamp_shapes(lights)], dtype=bool)
    lamps = ("lamp_position", "lamp_colour", "lamp_intensity", "lamp_shape")
    return lights | {k: np.asarray(lights[k])[kept] for k in lamps}


def shaped(e, to_light, shape):
    """Irradiance e (n,) times the lamp's falloff about its axis: c = -l.axis,
    t = clamp(scale c + offset, 0, 1), t (square (t - 1) + 1); a scale of 0: none."""
    axis, scale, offset, square = shape[0:3], shape[3], shape[4], shape[5]
    if scale == 0:
        return e
    along = (to_light[:, 0] * axis[0] + to_light[:, 1] * axis[1]) + to_light[
        :, 2
    ] * axis[2]
    t = np.minimum(np.maximum(offset - scale * along, F(0)), F(1))
    return e * (t * (square * (t - F(1)) + F(1)))


def lamp_irradiance_at(lights, k, points, normals):
    """Irradiance (n,) float32 of the lights' lamp k at points with normals (its
    `point_irradiance` and its shape's falloff) and the unit directions to it."""
    e, to_light = point_irradiance(
        lights["lamp_intensity"][k],
        lights["size"],
        lights["radius"],
        lights["lamp_position"][k],
        points,
        normals,
    )
    return shaped(e, to_light, lamp_shapes(lights)[k]), to_light


def spot_shape(axis, inner, outer):
    """A spot's shape: its axis (the way it emits) and glTF's cone, t^2 with
    t = clamp((c - cos outer) / max(cos inner - cos outer, LEAST_CONE))."""
    scale = 1.0 / max(np.cos(inner) - np.cos(outer), LEAST_CONE)
    return np.array([*axis, scale, -np.cos(outer) * scale, 1.0], dtype=F)


def lobe_shape(axis):
    """A cosine lobe's shape about its axis, 0 behind: t = clamp(c, 0, 1), t^1."""
    return np.array([*axis, 1.0, 0.0, 0.0], dtype=F)
