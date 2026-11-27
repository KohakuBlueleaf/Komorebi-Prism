"""A file's `lighting` entry (its sun, lamps and world in radiometric units) as a scene's
prepared lights: the sun, the lamps, the sky's coefficients and the background's
octahedral map."""

from pathlib import Path

import numpy as np

from prism_reference.direct.described.units import (
    MAP_SUFFIXES,
    euler_xyz,
    world_radiance,
)
from prism_reference.direct.lamps import SHAPE_WORDS, lobe_shape, spot_shape
from prism_reference.direct.sky import (
    OCTA_SIDE,
    octahedral_direction,
    sh_basis,
    texel_directions,
)
from prism_reference.io.hdr import read_hdr

F = np.float32
PLAIN_SIDE = 32  # the octahedral map of a world of one colour (one page a plane)
PLAIN_GRID = (64, 128)  # the directions a world of one colour is projected on
ROWS = 64  # map rows projected at once
UP = (0.0, 1.0, 0.0)  # the sun's direction when the file has no sun


def world_entry(world):
    """The entry's world as `world_radiance` reads it, None for no world, and the notes;
    a map the reference does not read gives the world's colour when it has one."""
    if world is None:
        return None, []
    strength = float(world["strength"])
    path = world.get("environment")
    if path is not None and Path(path).suffix.lower() in MAP_SUFFIXES:
        rotation = euler_xyz(np.asarray(world["rotation"], np.float64))
        return {"strength": strength, "map": read_hdr(path), "rotation": rotation}, []
    notes = []
    if path is not None:
        notes.append(
            f"world map {Path(path).name}: the reference reads Radiance .hdr only "
            f"({', '.join(MAP_SUFFIXES)}), so the world is its colour; convert the "
            "map with scripts/blender/world_map.py"
        )
    colour = np.asarray(world.get("colour", [0.0, 0.0, 0.0]), np.float64)
    if strength == 0 or not np.any(colour > 0):
        return None, notes
    return {"strength": strength, "colour": colour}, notes


def sky_coefficients(world):
    """The sky's 9 spherical-harmonic coefficients (9, 3) float32 of the world's
    radiance, projected over an equirectangular grid of directions (the map's own)."""
    if world is None:
        return np.zeros((9, 3), dtype=F)
    height, width = world["map"].shape[:2] if "map" in world else PLAIN_GRID
    sh = np.zeros((9, 3))
    directions, solids = texel_directions(height, width)
    for top in range(0, height, ROWS):
        d = directions[top : top + ROWS].reshape(-1, 3)
        solid = solids[top : top + ROWS].ravel()
        radiance = world_radiance(world, d)
        sh += np.einsum("nk,nc,n->kc", sh_basis(d), radiance, solid)
    return sh.astype(F)


def octahedral_of(world):
    """The background's octahedral map (side, side, 3) float32 of the world's radiance
    (zeros without a world): side OCTA_SIDE for a map, PLAIN_SIDE else."""
    side = OCTA_SIDE if world is not None and "map" in world else PLAIN_SIDE
    if world is None:
        return np.zeros((side, side, 3), dtype=F)
    c = (np.arange(side) + 0.5) / side * 2 - 1
    out = np.empty((side, side, 3), dtype=F)
    for top in range(0, side, ROWS):
        v, u = np.meshgrid(c[top : top + ROWS], c, indexing="ij")
        d = octahedral_direction(u, v).reshape(-1, 3)
        out[top : top + ROWS] = world_radiance(world, d).reshape(-1, side, 3)
    return out


def file_sun_sky(entry):
    """The prepared sun and sky of a file's `lighting` entry: sun direction (toward
    the sun) and irradiance, sky coefficients, octahedral map, turn 0, and notes."""
    world, notes = world_entry(entry["world"])
    sun = entry.get("sun")
    if sun is None:
        direction, irradiance = np.asarray(UP), np.zeros(3)
    else:
        direction = -np.asarray(sun["direction"], np.float64)
        irradiance = np.asarray(sun["irradiance"], np.float64)
    direction = direction / np.linalg.norm(direction)
    return {
        "sun_direction": direction.astype(F),
        "sun_irradiance": irradiance.astype(F),
        "sh": sky_coefficients(world),
        "octahedral": octahedral_of(world),
        "turn": 0.0,
        "notes": notes,
    }


def file_lamps(entry):
    """The lamps of a file's `lighting` entry: positions, colours and intensities
    (W/sr a unit of colour), float32, and their counts by kind."""
    lights = entry["lights"]
    position = np.array([x["position"] for x in lights], np.float32).reshape(-1, 3)
    colour = np.array([x["colour"] for x in lights], np.float32).reshape(-1, 3)
    intensity = np.array([x["intensity"] for x in lights], np.float32)
    kinds = [x.get("kind", "point") for x in lights]
    counts = {f"file_{kind}_lights": kinds.count(kind) for kind in sorted(set(kinds))}
    return position, colour, intensity, counts


def file_shapes(entry):
    """The lamps' shapes (L, SHAPE_WORDS) float32: a spot's cone, an area stand-in's
    cosine lobe, a point none."""
    out = np.zeros((len(entry["lights"]), SHAPE_WORDS), dtype=F)
    for k, lamp in enumerate(entry["lights"]):
        kind = lamp.get("kind", "point")
        if kind == "spot":
            out[k] = spot_shape(lamp["axis"], lamp["inner"], lamp["outer"])
        elif kind == "area":
            out[k] = lobe_shape(lamp["axis"])
    return out
