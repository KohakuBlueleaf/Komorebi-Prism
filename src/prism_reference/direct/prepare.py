"""Preparing a scene's lights file: the environment, the visibility bake, the lamps
and the shadow map, from the scene's `lighting` entry."""

import json
import os
import time

import numpy as np

from prism_reference.direct.described.lighting import (
    file_lamps,
    file_shapes,
    file_sun_sky,
)
from prism_reference.direct.lamps import find_lamps
from prism_reference.direct.shadow import SHADOW_SIDE, sun_view
from prism_reference.direct.sky import (
    LUMINANCE,
    OCTA_SIDE,
    environment,
    octahedral_map,
    read_radiance,
    sky_irradiance,
    sun_of,
)
from prism_reference.direct.visibility import VIS_RAYS, bake_visibility
from prism_reference.scene.public.lighting import fetch_environment, lighting_path
from prism_reference.scene.public.materials import load_materials
from prism_reference.scene.public.mesh import load_mesh
from prism_reference.scene.public.table import public_dir, table
from prism_reference.scene.public.views import EPS_SCALE
from prism_reference.trace.tree import triangles

F = np.float32


def scene_tree(name, data, mesh):
    """The ray tracer's tree of a scene: its triangles (`trace.tree.triangles`)."""
    return triangles(mesh)


def scene_lamps(entry, scene, materials):
    """The point lights of a `lighting` entry: its authored `lights`, each of intensity
    `lamp_scale`, else `find_lamps` (which reads `materials`). Positions, colours,
    intensities and counts."""
    if "lights" not in entry:
        return find_lamps(
            scene, materials, entry["merge_distance"], entry["lamp_scale"]
        )
    lights = entry["lights"]
    position = np.array([light["position"] for light in lights], dtype=np.float32)
    colour = np.array([light["colour"] for light in lights], dtype=np.float32)
    intensity = np.full(len(lights), entry["lamp_scale"], dtype=np.float32)
    return position, colour, intensity, {"authored_lights": len(lights)}


def scene_sun(entry, env_path):
    """The `environment` of a `lighting` entry and its turn (degrees); with an authored
    `sun` the map is turned to its azimuth and the sun is the authored one."""
    if "sun" not in entry:
        return environment(env_path, entry["turn"]), float(entry["turn"])
    radiance = read_radiance(env_path)
    own = sun_of(radiance, 0.0)[0].astype(np.float32).astype(np.float64)
    to_sun = -np.asarray(entry["sun"]["direction"], dtype=np.float64)
    to_sun /= np.linalg.norm(to_sun)
    turn = float(
        np.degrees(np.arctan2(own[2], own[0]) - np.arctan2(to_sun[2], to_sun[0]))
    )
    env = environment(env_path, turn, radiance)
    colour = np.asarray(entry["sun"]["colour"], dtype=np.float64)
    env["sun_direction"] = to_sun.astype(np.float32)
    env["sun_colour"] = (colour / (colour @ LUMINANCE)).astype(np.float32)
    return env, turn


def sky_visibility(name, data, mesh, workers, rebake, visibility):
    """The visibility a vertex and its counts: <scene>_visibility.npz (baked first when
    missing or rebake, with "bake"); with "open" and no file, 1 everywhere."""
    vis_path = public_dir(data) / f"{name}_visibility.npz"
    if visibility not in ("open", "bake"):
        raise ValueError(f"visibility {visibility!r}: one of open, bake")
    if visibility == "open" and not vis_path.exists():
        return np.ones(len(mesh["positions"]), dtype=F), {"visibility": "open"}
    if visibility == "bake" and (rebake or not vis_path.exists()):
        tree = scene_tree(name, data, mesh)
        p = mesh["positions"].astype(np.float64)
        eps = EPS_SCALE * float(np.linalg.norm(p.max(0) - p.min(0)))
        started = time.perf_counter()
        baked = bake_visibility(mesh["positions"], mesh["indices"], tree, eps, workers)
        bake = {
            "bake_seconds": time.perf_counter() - started,
            "rays": len(baked) * VIS_RAYS,
            "workers": workers,
            "eps": eps,
        }
        part = vis_path.with_name(f"{vis_path.stem}.{os.getpid()}.part.npz")
        np.savez(part, visibility=baked, counts=json.dumps(bake))
        part.replace(vis_path)
    with np.load(vis_path) as f:
        return f["visibility"], json.loads(str(f["counts"])) | {"visibility": "baked"}


def file_part(own, mesh, shadow_side, sun_view_of):
    """The arrays of the file's own lighting (the entry's `file`), each named `file_`
    and a LIGHT_KEYS name or `lamp_shape`: its sun, sky, background and lamps, and its
    shadow camera, texel and a 1 x 1 map of 0 when its sun's direction is not the
    defaults'; `sun_view_of` the defaults' (direction, camera, texel, map)."""
    env = file_sun_sky(own)
    position, colour, intensity, lamps = file_lamps(own)
    out = {
        "sun_direction": env["sun_direction"],
        "sun_irradiance": env["sun_irradiance"].astype(F),
        "sh": env["sh"],
        "octahedral": env["octahedral"],
        "turn": np.float32(env["turn"]),
        "lamp_position": position,
        "lamp_colour": colour,
        "lamp_intensity": intensity,
        "lamp_shape": file_shapes(own),
    }
    direction, camera, texel, depth = sun_view_of
    if not np.array_equal(env["sun_direction"], direction):
        camera, texel = sun_view(mesh, env["sun_direction"], shadow_side)
        depth = np.zeros((1, 1), dtype=F)
        out |= {"shadow_camera": camera, "shadow_texel": texel, "shadow_map": depth}
    counts = lamps | {"notes": env["notes"] + list(own.get("notes", []))}
    out["counts"] = json.dumps(counts)
    return {f"file_{key}": value for key, value in out.items()}


def prepare(
    name,
    data,
    workers=4,
    rebake=False,
    shadow_side=None,
    visibility="bake",
):
    """Writes <scene>_lighting.npz: the environment, the sky's visibility (`visibility`
    "bake": baked, kept in <scene>_visibility.npz unless rebake; "open": the kept one,
    else 1), the lamps, the sun's camera and a 1 x 1 shadow map of 0, and with the
    entry's `file` the file's own lighting beside them (`file_part`); path, counts."""
    entry = table()[name]["lighting"]
    (env_path,) = fetch_environment(entry["environment"], data)
    mesh, _ = load_mesh(name, data)
    materials = load_materials(name, data)[0] if "lights" not in entry else None
    counts = {"vertices": len(mesh["positions"])}
    visibility, bake = sky_visibility(name, data, mesh, workers, rebake, visibility)
    counts |= bake
    env, turn = scene_sun(entry, env_path)
    up = np.array([[0.0, 1.0, 0.0]], dtype=np.float32)
    horizontal = sky_irradiance(env["sh"], up)[0]
    sun_irradiance = (
        F(entry["sun_to_sky"]) * (horizontal @ LUMINANCE.astype(np.float32))
    ) * env["sun_colour"]
    started = time.perf_counter()
    if shadow_side is None:
        shadow_side = entry.get("shadow_side", SHADOW_SIDE)
    counts["shadow_side"] = shadow_side = int(shadow_side)
    camera, texel = sun_view(mesh, env["sun_direction"], shadow_side)
    depth = np.zeros((1, 1), dtype=F)
    counts["shadow_seconds"] = time.perf_counter() - started
    position, colour, intensity, lamps = scene_lamps(entry, mesh, materials)
    counts |= lamps
    counts["sun_share"], counts["turn"] = env["sun_share"], turn
    counts["sky_side"] = side = int(entry.get("sky_side", OCTA_SIDE))
    own = {}
    if "file" in entry:
        sun = (env["sun_direction"], camera, texel, depth)
        own = file_part(entry["file"], mesh, shadow_side, sun)
    out = lighting_path(name, data)
    part = out.with_name(f"{out.stem}.{os.getpid()}.part.npz")
    np.savez(
        part,
        visibility=visibility,
        sh=env["sh"],
        sun_direction=env["sun_direction"],
        sun_irradiance=sun_irradiance.astype(np.float32),
        octahedral=octahedral_map(env["environment"], 0.0, side),
        turn=np.float32(turn),
        shadow_map=depth,
        shadow_side=np.int32(shadow_side),
        shadow_camera=camera,
        shadow_texel=texel,
        lamp_position=position,
        lamp_colour=colour,
        lamp_intensity=intensity,
        counts=json.dumps(counts),
        **own,
    )
    part.replace(out)
    counts["bytes"] = os.path.getsize(out)
    return out, counts
