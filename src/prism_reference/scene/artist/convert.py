"""A glTF file through the scene description into a scene of the tables: the mesh file,
the materials file, the table entry and a report of the conversion."""

import json
import time

import numpy as np

from prism_common.paths import cache_root
from prism_reference.scene.artist.entry import entry_of
from prism_reference.scene.artist.materials import Textures, image_of, map_material
from prism_reference.scene.artist.source import source_of
from prism_reference.scene.description.flatten import draws, flatten
from prism_reference.scene.description.report import coverage
from prism_reference.scene.description.types import Note
from prism_reference.scene.importers import gltf, meshio
from prism_reference.scene.public.materials import KINDS
from prism_reference.scene.public.mesh import shared_vertices, vertex_shade
from prism_reference.scene.public.table import public_dir

MOST_TRIANGLES = 4_000_000
LEVELS = "levels"  # the cache root's folder of the images' mip chains
NO_MATERIAL = (
    0,
    np.array(meshio.DEFAULT_COLOUR),
    [-1] * 4,
    1,
    np.zeros(3),
    np.zeros(3),
)


def triangle_sources(scene):
    """Per drawn triangle, in `flatten`'s order: whether its primitive has uv0, and the
    count of drawn primitives carrying uv1."""
    has_uv, second = [], 0
    for mesh, _ in draws(scene):
        for prim in scene.meshes[mesh].primitives:
            has_uv.append(np.full(len(prim.indices), prim.uv0 is not None))
            second += prim.uv1 is not None
    found = np.concatenate(has_uv) if has_uv else np.zeros(0, dtype=bool)
    return found, second


def transformed(uv, use):
    """(..., 2) uv through a TextureUse's transform: scale, then rotation, then offset."""
    if use is None:
        return uv
    c, s = np.cos(use.rotation), np.sin(use.rotation)
    u, v = uv[..., 0] * use.scale[0], uv[..., 1] * use.scale[1]
    return np.stack([c * u + s * v + use.offset[0], c * v - s * u + use.offset[1]], -1)


def material_table(scene, material, has_uv, textures):
    """Rows (material 0 "(flat)", one per glTF material, then a flat row for each one
    drawn without uv0 that would sample a texture), names, per-triangle rows, mappings.
    """
    rows, names, mapping, row_of = [NO_MATERIAL], ["(flat)"], [], {}
    for m, item in enumerate(scene.materials):
        record, dropped = map_material(item, scene, textures.number)
        row_of[(m, True)] = len(rows)
        rows.append(record)
        names.append(item.name or f"material {m}")
        mapping.append({"name": names[-1], "dropped": dropped})
    for m in np.unique(material[(material >= 0) & ~has_uv]):
        record, dropped = map_material(
            scene.materials[m], scene, textures.number, False
        )
        if KINDS[record[0]] == "flat" and KINDS[rows[row_of[(m, True)]][0]] != "flat":
            row_of[(m, False)] = len(rows)
            rows.append(record)
            names.append(f"{names[row_of[(m, True)]]} (no uv0)")
            mapping.append({"name": names[-1], "dropped": dropped})
    lookup = np.zeros((len(scene.materials) + 1, 2), dtype=np.int32)
    for (m, uv), row in row_of.items():
        lookup[m, int(uv)] = row
        if (m, False) not in row_of:
            lookup[m, 0] = row_of[(m, True)]
    per_triangle = np.where(material >= 0, lookup[material, has_uv.astype(int)], 0)
    for item, row in zip(mapping, rows[1:], strict=True):
        kind, _, slots, exponent, specular, tau = row
        item |= {
            "kind": KINDS[kind],
            "exponent": int(exponent),
            "specular": [round(float(x), 6) for x in specular],
            "transmission": [round(float(x), 6) for x in tau],
            "slots": [int(s) for s in slots],
        }
    return rows, names, per_triangle.astype(np.int32), mapping


def colours_of(scene, material, textures):
    """Per triangle its flat colour (T, 3): base_color rgb times the linear mean of its
    base-colour texture when it has one; DEFAULT_COLOUR without a material."""
    table = np.array([meshio.DEFAULT_COLOUR] * (len(scene.materials) + 1))
    for m, item in enumerate(scene.materials):
        table[m] = item.base_color[:3]
        image = image_of(scene, item.base_color_texture)
        if image is not None:
            table[m] = table[m] * textures.mean(image)
    return table[material]


def corner_uv(scene, flat, material, has_uv):
    """Per triangle its corners' uv (T, 3, 2): uv0 through the base-colour transform,
    written as (u, 1 - v); 0 where the primitive has no uv0."""
    uv = flat["uv0"][flat["indices"]].astype(np.float64)
    order = np.argsort(material, kind="stable")
    counts = np.bincount(material[material >= 0])
    ends = np.count_nonzero(material < 0) + np.cumsum(counts)
    for m in np.flatnonzero(counts):
        use = scene.materials[m].base_color_texture
        if use is not None:
            pick = order[ends[m] - counts[m] : ends[m]]
            uv[pick] = transformed(uv[pick], use)
    uv[..., 1] = 1.0 - uv[..., 1]
    return np.where(has_uv[:, None, None], uv, 0.0).astype(np.float32)


def count_notes(mapping, second_primitives):
    """One `dropped` Note per name over every material's mapping."""
    counts = {}
    for item in mapping:
        for name in item["dropped"]:
            counts[name] = counts.get(name, 0) + 1
    notes = [Note("dropped", name, n) for name, n in counts.items()]
    if second_primitives:
        notes.append(Note("dropped", "second UV set", second_primitives, "primitives"))
    return notes


class Steps:
    """Seconds of each named step since the previous mark, in order."""

    def __init__(self):
        self.seconds, self.last = {}, time.perf_counter()

    def mark(self, name):
        """The time since the previous mark added to step `name`."""
        now = time.perf_counter()
        self.seconds[name] = self.seconds.get(name, 0.0) + now - self.last
        self.last = now


def convert(
    path,
    name,
    data,
    camera=None,
    most_triangles=MOST_TRIANGLES,
    licence="",
    attribution="",
    workers=4,
):
    """Writes <public>/<name>.npz and <public>/<name>_materials.npz from a glTF file;
    returns the table entry and the report (its `steps`: seconds of each step)."""
    steps = Steps()
    scene = gltf.load(path)
    steps.mark("import")
    flat = flatten(scene, most_triangles)
    steps.mark("flatten")
    material = flat["material"].astype(np.int64)
    has_uv, second = triangle_sources(scene)
    textures = Textures(scene, cache_root(data) / LEVELS)
    rows, names, per_triangle, mapping = material_table(
        scene, material, has_uv, textures
    )
    bases = {
        (image_of(scene, m.base_color_texture), "colour")
        for m in scene.materials
        if image_of(scene, m.base_color_texture) is not None
    }
    steps.mark("materials")
    textures.decode(sorted(bases), workers)
    colour = colours_of(scene, material, textures)
    steps.mark("textures")
    positions = flat["positions"].astype(np.float64)
    faces = flat["indices"].astype(np.int64)
    vp, vc, idx = shared_vertices(positions, faces, colour)
    shade = vertex_shade(vp, idx)
    steps.mark("shared_vertices")
    folder = public_dir(data)
    counts = {"triangles_total": len(idx), "vertices": len(vp)}
    np.savez(
        folder / f"{name}.npz",
        positions=vp.astype(np.float32),
        colors=np.clip(vc * shade[:, None], 0, 1).astype(np.float32),
        indices=idx.astype(np.int32),
        counts=json.dumps(counts),
    )
    kinds, base, slots, exponent, specular, tau = zip(*rows, strict=True)
    kinds = np.array(kinds, dtype=np.int32)
    steps.mark("writing")
    texels, mip, levels = textures.pack()
    steps.mark("textures")
    uv = corner_uv(scene, flat, material, has_uv)
    steps.mark("uv")
    used = np.bincount(kinds[per_triangle], minlength=len(KINDS))
    material_counts = {
        "triangles": len(idx),
        "materials": len(names),
        "textures": len(levels),
        "texel_bytes": int(texels.size),
        "triangles_by_kind": {k: int(n) for k, n in zip(KINDS, used)},
    }
    np.savez(
        folder / f"{name}_materials.npz",
        uv=uv,
        material=per_triangle,
        light=shade[idx].astype(np.float32),
        kind=kinds,
        base_colour=np.array(base, dtype=np.float32),
        textures=np.array(slots, dtype=np.int32),
        exponent=np.array(exponent, dtype=np.int32),
        specular=np.array(specular, dtype=np.float32),
        transmission=np.array(tau, dtype=np.float32),
        texels=texels,
        mip=mip,
        levels=levels,
        names=json.dumps(names),
        texture_names=json.dumps(textures.names()),
        counts=json.dumps(material_counts),
    )
    steps.mark("writing")
    entry, view, view_notes = entry_of(
        scene, vp, len(idx), camera, licence, attribution
    )
    entry["title"] = name
    entry["source"] = source_of(path, scene)
    notes = count_notes(mapping, second) + view_notes
    report = {
        "coverage": coverage(scene),
        "triangles": len(idx),
        "vertices": len(vp),
        "materials_by_kind": {
            k: int(n) for k, n in zip(KINDS, np.bincount(kinds, minlength=len(KINDS)))
        },
        "triangles_by_kind": material_counts["triangles_by_kind"],
        "textures": [
            {"image": int(i), "role": role, "name": n}
            for (i, role), n in zip(textures.jobs, textures.names(), strict=False)
        ]
        or [{"image": -1, "role": "colour", "name": "(white)"}],
        "texel_bytes": int(texels.size),
        "mapping": mapping,
        "view": view,
        "camera_nodes": [n.name for n in scene.nodes if n.camera != -1],
        "notes": [
            {"kind": n.kind, "what": n.what, "count": n.count, "detail": n.detail}
            for n in notes
        ],
    }
    steps.mark("entry")
    report["steps"] = {k: round(v, 3) for k, v in steps.seconds.items()}
    return entry, report
