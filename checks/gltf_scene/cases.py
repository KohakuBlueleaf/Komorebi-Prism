"""The cases: each material's mapping, the textured quad's corners looked up in the written
texels, the files read by the reference's loaders and the view's camera, the entry's keys.
"""

import json

import numpy as np

from checks.gltf_scene import scene
from checks.scene_description.roundtrip import rodrigues
from prism_reference.material.texture import texel_xy
from prism_reference.scene.public.materials import KINDS, MATERIAL_KEYS, load_materials
from prism_reference.scene.public.mesh import load_mesh
from prism_reference.scene.public.table import TABLE
from prism_reference.scene.public.views import make_view

RESULTS = []
TOLERANCE = 1e-5
# The dtype and the number of dimensions of each array of the materials file.
TYPES = {
    "uv": ("float32", 3),
    "material": ("int32", 1),
    "light": ("float32", 2),
    "kind": ("int32", 1),
    "base_colour": ("float32", 2),
    "textures": ("int32", 2),
    "exponent": ("int32", 1),
    "specular": ("float32", 2),
    "transmission": ("float32", 2),
    "texels": ("uint8", 1),
    "mip": ("int64", 3),
    "levels": ("int32", 1),
}


def same(case, got, want, relative=False):
    """Records whether `got` equals `want`: exact for integers and text, else within
    TOLERANCE (relative to |want| when `relative`)."""
    g, w = np.asarray(got), np.asarray(want)
    if g.shape != w.shape:
        equal = False
    elif g.dtype.kind in "fc" or w.dtype.kind in "fc":
        scale = np.maximum(np.abs(w), 1e-300) if relative else 1.0
        equal = bool(np.all(np.abs(g - w) / scale <= TOLERANCE))
    else:
        equal = bool(np.array_equal(g, w))
    RESULTS.append({"case": case, "equal": equal})
    if not equal:
        RESULTS[-1]["got"], RESULTS[-1]["want"] = repr(got)[:200], repr(want)[:200]
    return equal


def kinds_case(materials, report):
    """Each material's kind, base, slots, exponent, specular, transmission and
    shadow."""
    names = [item["name"] for item in report["mapping"]]
    rows = [(n, *expect) for n, _, expect in scene.KINDS]
    rows.append((*scene.NO_UV, 30, [0.04] * 3, [0.0] * 3))
    for name, kind, base, slots, exponent, specular, tau in rows:
        m = names.index(name) + 1
        same(f"{name}: kind", KINDS[int(materials["kind"][m])], kind)
        same(f"{name}: base", materials["base_colour"][m], base)
        same(f"{name}: slots", materials["textures"][m], slots)
        same(f"{name}: exponent", int(materials["exponent"][m]), exponent)
        same(f"{name}: specular", materials["specular"][m], specular)
        same(f"{name}: transmission", materials["transmission"][m], tau)
        shadow = scene.SHADOWS.get(name, [0.0] * 3)
        same(f"{name}: shadow", materials["shadow"][m], shadow)
    same("textures numbered", len(materials["levels"]), 2)
    same("rows", len(materials["kind"]), len(rows) + 1)


def corners_case(materials):
    """The textured quad: each corner's uv, looked up at level 0, gives the texel glTF
    puts at its transformed uv (the quad's two triangles come first)."""
    same("textured quad: material", materials["material"][:2], [scene.TEXTURED] * 2)
    for t, corners in enumerate(scene.QUAD_INDICES):
        uv = materials["uv"][t]
        tex = np.zeros(3, dtype=np.int64)
        x, y, entry = texel_xy(materials, tex, tex, uv[:, 0], uv[:, 1])
        start = entry[:, 0] + (y * entry[:, 1] + x) * 4
        got = materials["texels"][start[:, None] + np.arange(3)]
        target = scene.TARGETS[corners]
        frac = target - np.floor(target)
        row, column = (frac[:, 1] * 2).astype(int), (frac[:, 0] * 2).astype(int)
        same(f"textured quad: triangle {t} colours", got, scene.COLOURS[row, column])


def view_case(name, data):
    """`make_view` of the scene's one view against the file's camera."""
    view = make_view(f"{name}_camera", data)
    camera = view["camera"].astype(np.float64)
    trs = scene.CAMERA_TRS
    eye = np.add(scene.CAMERA_PARENT, trs["translation"])
    forward = rodrigues(trs["axis"], trs["angle"]) @ [0.0, 0.0, -1.0]
    yfov, aspect = scene.CAMERA["yfov"], scene.CAMERA["aspectRatio"]
    focal = 512.0 / (aspect * np.tan(yfov / 2))
    same("view: eye", camera[0:3], eye, relative=True)
    same("view: forward", camera[9:12], forward, relative=True)
    same("view: focal length", camera[12], focal, relative=True)
    same("view: near", camera[15], scene.CAMERA["znear"], relative=True)


def files_case(name, data):
    """The mesh and materials files through `load_mesh` and `load_materials`."""
    mesh, counts = load_mesh(name, data)
    same("mesh: keys", sorted(mesh), ["colors", "indices", "positions"])
    same(
        "mesh: counts",
        [counts["triangles_total"], counts["vertices"]],
        [len(mesh["indices"]), len(mesh["positions"])],
    )
    materials, _ = load_materials(name, data)
    same("materials: keys", sorted(materials), sorted(MATERIAL_KEYS))
    for key, (dtype, ndim) in TYPES.items():
        array = materials[key]
        same(f"materials: {key} type", [str(array.dtype), array.ndim], [dtype, ndim])
    triangles = len(mesh["indices"])
    for key in ("uv", "material", "light"):
        same(f"materials: {key} per triangle", len(materials[key]), triangles)
    return materials


def entry_case(entry):
    """Every key of Sponza's entry, and of its lighting, present with the same type."""
    sponza = json.loads(TABLE.read_text())["sponza"]
    entry = json.loads(json.dumps(entry))
    for key, value in sponza.items():
        same(f"entry: {key}", type(entry.get(key)).__name__, type(value).__name__)
    for key, value in sponza["lighting"].items():
        got = type(entry["lighting"].get(key)).__name__
        same(f"entry: lighting {key}", got, type(value).__name__)
    same(
        "entry: sun", sorted(entry["lighting"].get("sun", {})), ["colour", "direction"]
    )
    same("entry: lights", len(entry["lighting"].get("lights", [])), 2)


def untextured_case(name, data):
    """A file without any image: the materials load with one white texel, no slot used."""
    materials, counts = load_materials(name, data)
    same("no image: mip rows", len(materials["mip"]), 1)
    same("no image: levels", materials["levels"], [1])
    same("no image: texels", materials["texels"], [255] * 4)
    same("no image: slots", materials["textures"], np.full((2, 4), -1))
    same("no image: counted", counts["textures"], 1)
