"""The scene description's lights as radiometric numbers: radiant intensity (W/sr),
irradiance (W/m^2) and radiance (W/(m^2 sr)) per colour channel."""

from pathlib import Path

import numpy as np

from prism_reference.io.hdr import read_hdr

LUMENS_PER_WATT = 683.0  # the exporter's PBR_WATTS_TO_LUMENS
LEAST_CONE = 1e-3  # glTF's floor on cos(inner) - cos(outer)
SHAPES = ("RECTANGLE", "SQUARE", "DISK", "ELLIPSE")
ROUND = ("DISK", "ELLIPSE")
BLENDER_AXES = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]])
MAP_SUFFIXES = (".hdr",)


class NotCarried(ValueError):
    """A light or world the reference cannot express; its message names what."""


def unit(v):
    """Rows of v (..., 3) scaled to length 1."""
    v = np.asarray(v, dtype=np.float64)
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-300)


def point_intensity(light):
    """Radiant intensity (3,) W/sr: I = colour x candela / 683."""
    return np.asarray(light.color, np.float64) * light.intensity / LUMENS_PER_WATT


def spot_attenuation(cosine, inner, outer):
    """glTF's cone: t = clamp((cos - cos outer) / max(cos inner - cos outer, 1e-3)),
    attenuation t^2."""
    scale = 1.0 / max(np.cos(inner) - np.cos(outer), LEAST_CONE)
    t = np.clip((cosine - np.cos(outer)) * scale, 0.0, 1.0)
    return t * t


def sun_irradiance(light):
    """Irradiance (3,) W/m^2 on a plane facing the sun: E = colour x lux / 683."""
    return np.asarray(light.color, np.float64) * light.intensity / LUMENS_PER_WATT


def light_axes(world, kind):
    """The light's position (3,), emitting direction (3,) and local x and y axes (3,)
    in the description's axes: punctual lights glTF's -Z, area lights Blender's -Z."""
    m = np.asarray(world, dtype=np.float64)
    linear = m[:3, :3]
    if kind == "area":
        x, y, z = (linear @ BLENDER_AXES[:, k] for k in range(3))
    else:
        x, y, z = (linear @ np.eye(3)[k] for k in range(3))
    return m[:3, 3], unit(-z), x, y


def area_extent(light, world):
    """Centre (3,), half axes u, v (3,) (local x and y times half the size, the node's
    scale kept), unit emitting normal (3,) and area (m^2) of an area light."""
    if light.shape not in SHAPES:
        raise NotCarried(f"area light shape {light.shape!r}")
    centre, normal, x, y = light_axes(world, "area")
    sx = float(light.size[0])
    sy = sx if light.shape in ("SQUARE", "DISK") else float(light.size[1])
    u, v = x * sx / 2, y * sy / 2
    area = 4.0 * np.linalg.norm(np.cross(u, v))
    if light.shape in ROUND:
        area *= np.pi / 4
    return centre, u, v, normal, area


def area_radiance(light, area):
    """Radiance (3,) of a one-sided Lambertian emitter: L = colour x watts / (pi A)."""
    if area <= 0:
        return np.zeros(3)
    return np.asarray(light.color, np.float64) * light.intensity / (np.pi * area)


def euler_xyz(angles):
    """The rotation (3, 3) of Euler angles (x, y, z) in radians applied x first."""
    cx, cy, cz = np.cos(angles)
    sx, sy, sz = np.sin(angles)
    rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return rz @ ry @ rx


def world_light(world, folder):
    """The world as {"strength", "colour"} or {"strength", "map", "rotation"}; None when
    it gives no light; NotCarried for a map the reference does not read."""
    if world is None:
        return None
    strength = float(world.strength)
    if world.environment is None:
        colour = np.asarray(world.color, np.float64)
        if strength == 0 or not np.any(colour > 0):
            return None
        return {"strength": strength, "colour": colour}
    path = Path(folder) / world.environment
    if path.suffix.lower() not in MAP_SUFFIXES:
        raise NotCarried(f"world map format {path.suffix.lower()}")
    if strength == 0:
        return None
    rotation = euler_xyz(np.asarray(world.rotation, np.float64))
    return {"strength": strength, "map": read_hdr(path), "rotation": rotation}


def equirect_texel(d, height, width):
    """Row and column of Blender's equirectangular lookup of directions d (n, 3) in
    Blender's axes: u = 1/2 - atan2(y, x) / 2 pi, v = atan2(z, hypot(x, y)) / pi + 1/2.
    """
    u = 0.5 - np.arctan2(d[:, 1], d[:, 0]) / (2 * np.pi)
    v = np.arctan2(d[:, 2], np.hypot(d[:, 0], d[:, 1])) / np.pi + 0.5
    column = np.clip((u * width).astype(np.int64), 0, width - 1)
    row = np.clip(((1.0 - v) * height).astype(np.int64), 0, height - 1)
    return row, column


def world_radiance(entry, d):
    """Radiance (n, 3) of the world toward unit directions d (n, 3) (description axes):
    strength x colour, or strength x the map's nearest texel."""
    if "colour" in entry:
        return np.broadcast_to(entry["strength"] * entry["colour"], d.shape)
    blender = d @ BLENDER_AXES
    turned = blender @ entry["rotation"].T
    row, column = equirect_texel(turned, *entry["map"].shape[:2])
    return entry["strength"] * entry["map"][row, column].astype(np.float64)
