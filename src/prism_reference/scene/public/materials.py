"""A public scene's materials file: each material's kind and numbers from its MTL
statements, the textures as mip chains, written and read."""

import concurrent.futures
import json
import re
from pathlib import Path

import numpy as np

from prism_reference.scene.importers import meshio
from prism_reference.scene.public.mesh import (
    load_mesh,
    read_parts,
    shared_vertices,
    vertex_shade,
)
from prism_reference.scene.public.table import (
    fetch,
    is_view,
    public_dir,
    table,
    views,
)
from prism_reference.scene.public.textures import (
    LEVELS_VERSION,
    MIP_LEVELS,
    TextureFiles,
    decode_levels,
)

# The kinds of shader (the number is the kind's code) and a material's texture slots.
KINDS = ("flat", "textured", "masked", "lit", "emissive", "transparent")
SLOTS = ("albedo", "mask", "normal", "specular")
EMISSIVE_MIN = 0.5  # a material whose Ke reaches this in a channel glows
EXPONENT_RANGE = (1, 1024)
NUMBER = re.compile(r"[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?")
MATERIAL_KEYS = (
    "uv",
    "material",
    "light",
    "kind",
    "base_colour",
    "textures",
    "exponent",
    "specular",
    "transmission",
    "shadow",
    "texels",
    "mip",
    "levels",
    "uv_maps",
    "normal_scale",
)


def numbers(text, default):
    """Up to three numbers at the start of a statement's text (the last repeated to
    three; text after a number is ignored), else default (3,)."""
    values = []
    for word in (text or "").split()[:3]:
        match = NUMBER.match(word)
        if not match:
            break
        values.append(float(match.group()))
    if not values:
        return np.broadcast_to(np.asarray(default, dtype=np.float64), 3).copy()
    return np.array((values + values[-1:] * 2)[:3], dtype=np.float64)


def transmission(statements):
    """The transmission colour (3,) of a material's MTL statements, in 0..1: 1 - `Tf`
    when it gives `Tf`, else `Tr` in every channel, else 1 - `d`."""
    if "Tf" in statements:
        tau = 1.0 - numbers(statements["Tf"], 1.0)
    elif "Tr" in statements:
        tau = numbers(statements["Tr"], 0.0)[:1].repeat(3)
    else:
        tau = 1.0 - numbers(statements.get("d"), 1.0)[:1].repeat(3)
    return np.clip(tau, 0.0, 1.0)


def material_record(statements, files, texture_number, options=None):
    """(kind, base colour, texture numbers by slot, exponent, specular colour,
    transmission) of one material's MTL statements; texture_number(file, role) numbers
    the files; options: the table's `materials` keys."""
    found = {
        key: files.find(statements.get(key))
        for key in ("map_Kd", "map_d", "map_bump", "bump", "map_Ks", "map_Ke")
    }
    albedo, emit, mask = found["map_Kd"], found["map_Ke"], found["map_d"]
    normal, specular = found["map_bump"] or found["bump"], found["map_Ks"]
    glow = numbers(statements.get("Ke"), (0.0, 0.0, 0.0))
    slots = [-1, -1, -1, -1]
    base = numbers(statements.get("Kd"), meshio.DEFAULT_COLOUR)
    options = options or {}
    if options.get("black_kd_is_texture") and albedo and not base.any():
        base = np.ones(3)
    exponent = int(
        np.clip(np.rint(numbers(statements.get("Ns"), 1.0)[0]), *EXPONENT_RANGE)
    )
    specular_colour = numbers(statements.get("Ks"), (0.0, 0.0, 0.0))
    tau = transmission(statements)
    if emit or glow.max() >= EMISSIVE_MIN:
        kind = "emissive"
        if emit:
            slots[0], base = texture_number(emit, "colour"), np.ones(3)
        else:
            base = np.clip(glow / options.get("emission_scale", 1.0), 0.0, 1.0)
    elif (tau > 0).any() and not (albedo and mask):
        kind = "transparent"
        if albedo:
            slots[0] = texture_number(albedo, "colour")
    elif albedo is None:
        kind = "flat"
    else:
        slots[0] = texture_number(albedo, "colour")
        if mask:
            kind = "masked"
            if mask != albedo:
                slots[1] = texture_number(mask, "mask")
        elif normal or specular:
            kind = "lit"
            if normal:
                slots[2] = texture_number(normal, "normal")
            if specular:
                slots[3] = texture_number(specular, "colour")
        else:
            kind = "textured"
    if kind != "transparent":
        tau = np.zeros(3)
    return KINDS.index(kind), base, slots, exponent, specular_colour, tau


def convert_materials(name, data, workers=4):
    """Writes <public>/<name>_materials.npz: per triangle of <name>.npz its corners'
    texture coordinates, material and light term; the material table; the textures."""
    entry = table()[name]
    if "materials" not in entry:
        raise ValueError(f"{name}: the table gives it no materials")
    mesh, _ = load_mesh(name, data)
    downloads = {
        p.name: p for p in fetch(name, data) + fetch(name, data, "texture_files")
    }
    archives = {
        stem: downloads[file]
        for stem, file in entry["materials"].get("archives", {}).items()
    }
    pos, faces, colour, _, meshes = read_parts(name, data, with_uv=True)
    vp, _, idx = shared_vertices(pos, faces, colour)
    if not np.array_equal(idx, mesh["indices"]):
        raise ValueError(
            f"{name}: the scene file is not this conversion's; fetch again"
        )
    light = vertex_shade(vp, idx)[idx]
    # Material 0 is flat: the ground, triangles without coordinates or material.
    names = ["(flat)"]
    rows = [(0, np.array(meshio.DEFAULT_COLOUR), [-1] * 4, 1, np.zeros(3), np.zeros(3))]
    jobs, numbers_of = [], {}

    def texture_number(file, role):
        key = (str(file[0]), file[1], role)
        if key not in numbers_of:
            numbers_of[key] = len(jobs)
            jobs.append(key)
        return numbers_of[key]

    count = len(idx)
    uv = np.zeros((count, 3, 2), dtype=np.float32)
    material = np.zeros(count, dtype=np.int32)
    first = 0
    for part, read in zip(entry["meshes"], meshes):
        triangles = len(read.faces)
        if read.uv is None:
            first += triangles
            continue
        files = TextureFiles(downloads[part["file"]], part["member"], archives)
        number = np.zeros(len(read.material_names) + 1, dtype=np.int32)
        for k, material_name in enumerate(read.material_names):
            record = material_record(
                read.statements.get(material_name, {}),
                files,
                texture_number,
                entry["materials"],
            )
            number[k] = len(names)
            names.append(material_name)
            rows.append(record)
        has_uv = ~np.isnan(read.uv).any(axis=(1, 2))
        own = np.where(has_uv & (read.material >= 0), number[read.material], 0)
        span = slice(first, first + triangles)
        material[span] = own
        uv[span] = np.where(has_uv[:, None, None], np.nan_to_num(read.uv), 0)
        first += triangles
    kinds, bases, slots, exponents, speculars, taus = zip(*rows, strict=True)
    kinds = np.array(kinds, dtype=np.int32)
    sources = [(Path(a), m, r) for a, m, r in jobs]
    if workers > 1:
        with concurrent.futures.ProcessPoolExecutor(workers) as pool:
            chains = list(pool.map(decode_levels, sources))
    else:
        chains = [decode_levels(job) for job in sources]
    mip = np.zeros((len(chains), MIP_LEVELS, 3), dtype=np.int64)
    level_count = np.zeros(len(chains), dtype=np.int32)
    offset, blocks = 0, []
    for t, chain in enumerate(chains):
        level_count[t] = len(chain)
        for level, image in enumerate(chain):
            mip[t, level] = offset, image.shape[1], image.shape[0]
            blocks.append(image.reshape(-1))
            offset += image.size
    used = np.bincount(kinds[material], minlength=len(KINDS))
    counts = {
        "triangles": count,
        "materials": len(names),
        "textures": len(chains),
        "texel_bytes": offset,
        "triangles_by_kind": {k: int(n) for k, n in zip(KINDS, used)},
    }
    out = public_dir(data) / f"{name}_materials.npz"
    part = out.with_name(f"{out.name}.part")
    with open(part, "wb") as handle:
        np.savez(
            handle,
            uv=uv,
            material=material,
            light=light.astype(np.float32),
            kind=kinds,
            base_colour=np.array(bases, dtype=np.float32),
            textures=np.array(slots, dtype=np.int32),
            exponent=np.array(exponents, dtype=np.int32),
            specular=np.array(speculars, dtype=np.float32),
            transmission=np.array(taus, dtype=np.float32),
            texels=np.concatenate(blocks) if blocks else np.zeros(0, np.uint8),
            mip=mip,
            levels=level_count,
            names=json.dumps(names),
            texture_names=json.dumps([f"{Path(a).name}:{m} ({r})" for a, m, r in jobs]),
            counts=json.dumps(counts),
            versions=json.dumps(versions()),
        )
    part.replace(out)
    return out


def load_materials(name, data):
    """The materials of a converted scene (or of a view's scene): the arrays of
    MATERIAL_KEYS and the counts; missing or made at other versions, an error naming
    the command that writes it."""
    if is_view(name):
        name = views()[name][0]
    path = public_dir(data) / f"{name}_materials.npz"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing; write it with: {rebuild_command(name)}"
        )
    with np.load(path) as f:
        made = json.loads(str(f["versions"])) if "versions" in f.files else None
        if made != versions():
            raise ValueError(
                f"{path} was made at {made}, today's is {versions()}; "
                f"write it again with: {rebuild_command(name)}"
            )
        found = {k: f[k] for k in MATERIAL_KEYS if k in f.files}
        counts = json.loads(str(f["counts"]))
    return with_defaults(found), counts


def versions():
    """The versions a materials file's content is made at (kept in it as `versions`)."""
    return {"levels": LEVELS_VERSION}


def made_now(path):
    """True when the materials file at `path` was made at today's versions."""
    with np.load(path) as f:
        made = json.loads(str(f["versions"])) if "versions" in f.files else None
    return made == versions()


def rebuild_command(name):
    """The command that writes scene `name`'s materials file: an opened scene's open
    of its source file, else the public scenes' materials."""
    source = table().get(name, {}).get("source", {}).get("file")
    if "opened" in table().get(name, {}) and source:
        return f"python -m prism_cli open {source}"
    return f"python scripts/data/public_scenes.py materials {name}"


def with_defaults(materials):
    """The materials with a transmission of 0 (M, 3) added when they have none, a
    shadow (the sun's light a surface lets through, M, 3) of 1, slot uv maps of the
    identity (M, 4, 2, 3) and a normal scale of 1 (M,)."""
    rows = len(materials["kind"])
    zeros = np.zeros((rows, 3), dtype=np.float32)
    transmission = materials.get("transmission", zeros)
    shadow = materials.get("shadow", np.ones((rows, 3), dtype=np.float32))
    identity = np.tile(np.eye(3, dtype=np.float32)[:2], (rows, 4, 1, 1))
    return {
        **materials,
        "transmission": transmission,
        "shadow": shadow,
        "uv_maps": materials.get("uv_maps", identity),
        "normal_scale": materials.get("normal_scale", np.ones(rows, np.float32)),
    }


def export_materials(materials, folder):
    """Writes each array of the materials as <folder>/<key>.npy, the C++ input (a
    missing transmission as 0, `with_defaults`)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    materials = with_defaults(materials)
    for key in MATERIAL_KEYS:
        np.save(folder / f"{key}.npy", materials[key])
    return folder
