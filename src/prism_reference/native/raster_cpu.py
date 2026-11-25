"""Running the C++ rasterizer (raster/raster_cpu.cpp) on a scene and reading its
outputs."""

import json
import subprocess
from pathlib import Path

import numpy as np

from prism_common.paths import data_root
from prism_reference.material.texture import TEXEL_LINEAR
from prism_reference.native.build import RASTER, build
from prism_reference.scene.files import export_npy, save_scene
from prism_reference.scene.generated import make_preset
from prism_reference.scene.public.materials import export_materials, load_materials
from prism_reference.scene.public.table import is_view, views
from prism_reference.scene.public.views import make_view

KEYS = ("colour", "depth", "tri", "tile_counts")


def ensure_scene(name):
    """Writes <data>/<name>.npz and <name>/*.npy if missing; returns the folder (a
    preset is generated, a public view made from its converted mesh)."""
    folder = data_root() / name
    if not (data_root() / f"{name}.npz").exists() or not folder.exists():
        if is_view(name):
            scene = make_view(name, data_root())
        else:
            scene = make_preset(name)
        export_npy(scene, folder)  # the .npz last: it says the folder is whole
        save_scene(data_root() / f"{name}.npz", scene)
    return folder


def materials_folder(view):
    """The materials of a view's scene as .npy files for the C++ binary, written on
    first use to <data>/<scene>_materials/ (with the albedo byte table)."""
    name = views()[view][0]
    folder = data_root() / f"{name}_materials"
    if not (folder / "texel_linear.npy").exists():
        materials, _ = load_materials(name, data_root())
        export_materials(materials, folder)
        np.save(folder / "texel_linear.npy", TEXEL_LINEAR)
    return folder


def load_outputs(folder):
    """The four output arrays a binary saved in a folder."""
    return {key: np.load(Path(folder) / f"{key}.npy") for key in KEYS}


def run_json(command):
    """Runs a binary that prints one JSON line; that line as a dict."""
    done = subprocess.run(command, capture_output=True, text=True, check=True)
    return json.loads(done.stdout.strip().splitlines()[-1])


def run_cpu(scene, threads, out, repetitions=1, materials=False):
    """Runs the C++ rasterizer on a scene into the folder `out`, FILL on `threads`
    (materials: SHADE too, on one thread); its record, None without a compiler."""
    executable = build(str(RASTER / "raster_cpu.cpp"), "raster_cpu")
    if executable is None:
        return None
    command_line = [executable, "--scene", ensure_scene(scene)]
    if materials:
        command_line += ["--materials", materials_folder(scene)]
    Path(out).mkdir(parents=True, exist_ok=True)
    command_line += ["--threads", threads, "--reps", repetitions, "--out", out]
    return run_json([str(c) for c in command_line])
