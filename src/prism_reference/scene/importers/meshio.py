"""OBJ (with MTL) and PLY meshes in numpy: fans, flat colours by material, degenerate
triangles dropped and counted; on request an OBJ's texture coordinates and materials."""

import gzip
import re
import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

DEFAULT_COLOUR = (0.7, 0.7, 0.7)
PLY_TYPES = {
    "char": "i1",
    "int8": "i1",
    "uchar": "u1",
    "uint8": "u1",
    "short": "i2",
    "int16": "i2",
    "ushort": "u2",
    "uint16": "u2",
    "int": "i4",
    "int32": "i4",
    "uint": "u4",
    "uint32": "u4",
    "float": "f4",
    "float32": "f4",
    "double": "f8",
    "float64": "f8",
}


@dataclass
class Mesh:
    """Triangles of a read file and what was dropped or missing on the way."""

    positions: np.ndarray
    faces: np.ndarray
    colour: np.ndarray
    counts: dict = field(default_factory=dict)
    # with_uv only: corner uv (T, 3, 2), material (T,), names, MTL statements
    uv: np.ndarray | None = None
    material: np.ndarray | None = None
    material_names: list | None = None
    statements: dict | None = None


def fan(starts, sizes, flat):
    """Triangles (0, k, k + 1) of every polygon given by its start and size in flat."""
    sizes = np.asarray(sizes, dtype=np.int64)
    starts = np.asarray(starts, dtype=np.int64)
    per = np.maximum(sizes - 2, 0)
    owner = np.repeat(np.arange(len(sizes)), per)
    k = np.arange(int(per.sum())) - np.repeat(np.cumsum(per) - per, per) + 1
    first = flat[starts[owner]]
    return (
        np.stack([first, flat[starts[owner] + k], flat[starts[owner] + k + 1]], 1),
        owner,
    )


def drop_degenerate(positions, faces):
    """Mask of triangles to keep and counts of each kind of degenerate one dropped."""
    a, b, c = faces[:, 0], faces[:, 1], faces[:, 2]
    repeated = (a == b) | (b == c) | (a == c)
    p = positions[faces]
    same = (p[:, 0] == p[:, 1]).all(1) | (p[:, 1] == p[:, 2]).all(1)
    same |= (p[:, 0] == p[:, 2]).all(1)
    same &= ~repeated
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    flat = (n == 0).all(axis=1) & ~repeated & ~same
    keep = ~(repeated | same | flat)
    counts = {
        "dropped_repeated_vertex": int(repeated.sum()),
        "dropped_equal_positions": int(same.sum()),
        "dropped_collinear": int(flat.sum()),
    }
    return keep, counts


def finish(positions, faces, colour, counts, uv=None, material=None):
    """The mesh with degenerate triangles removed and the counts recorded."""
    keep, dropped = drop_degenerate(positions, faces)
    counts = {**counts, **dropped, "triangles": int(keep.sum())}
    mesh = Mesh(positions, faces[keep], colour[keep], counts)
    if uv is not None:
        mesh.uv, mesh.material = uv[keep], material[keep]
    return mesh


def parse_mtl(text):
    """{material name: diffuse colour (3,)} of an MTL file's text."""
    colours, name = {}, None
    for line in text.splitlines():
        words = line.split()
        if not words:
            continue
        if words[0] == "newmtl":
            name = " ".join(words[1:])
            colours.setdefault(name, None)
        elif words[0] == "Kd" and name is not None and len(words) >= 4:
            colours[name] = tuple(float(w) for w in words[1:4])
    return colours


def parse_statements(text):
    """{material name: {statement: rest of its line}} of an MTL file's text."""
    statements, name = {}, None
    for line in text.splitlines():
        words = line.split(None, 1)
        if not words:
            continue
        if words[0] == "newmtl":
            name = " ".join(words[1:])
            statements.setdefault(name, {})
        elif name is not None and len(words) == 2:
            statements[name][words[0]] = words[1].strip()
    return statements


def parse_obj(text, materials, with_uv=False):
    """Mesh of an OBJ file's text; `materials` maps names to diffuse colours.

    with_uv: also the corners' texture coordinates and each triangle's material.
    """
    verts, flat, starts, sizes, face_mtl = [], [], [], [], []
    names, current, n_verts = {}, -1, 0
    texcoords, flat_uv, n_texcoords = [], [], 0
    for line in text.splitlines():
        if line.startswith("v "):
            verts.append(line[2:])
            n_verts += 1
        elif line.startswith("f "):
            words = line[2:].split()
            ids = [int(w.split("/", 1)[0]) for w in words]
            starts.append(len(flat))
            sizes.append(len(ids))
            flat += [i - 1 if i > 0 else n_verts + i for i in ids]
            face_mtl.append(current)
            if with_uv:
                for w in words:
                    parts = w.split("/")
                    k = int(parts[1]) if len(parts) > 1 and parts[1] else 0
                    flat_uv.append(k - 1 if k > 0 else (n_texcoords + k if k else -1))
        elif with_uv and line.startswith("vt "):
            texcoords.append((line[3:].split() + ["0", "0"])[:2])
            n_texcoords += 1
        elif line.startswith("usemtl"):
            name = line[6:].strip()
            current = names.setdefault(name, len(names))
    positions = np.array(" ".join(verts).split(), dtype=np.float64).reshape(-1, 3)
    faces, owner = fan(starts, sizes, np.array(flat, dtype=np.int64))
    # One row per material; the last row (index -1) is for faces before any usemtl.
    table = np.array([DEFAULT_COLOUR] * (len(names) + 1), dtype=np.float64)
    missing = 0
    for name, k in names.items():
        colour = materials.get(name)
        if colour is None:
            missing += 1
        else:
            table[k] = colour
    mtl = np.array(face_mtl, dtype=np.int64)[owner]
    counts = {
        "polygons": len(sizes),
        "materials": len(names),
        "materials_without_colour": missing,
        "triangles_without_material": int((mtl < 0).sum()),
    }
    if not with_uv:
        return finish(positions, faces, table[mtl], counts)
    corner_uv, _ = fan(starts, sizes, np.array(flat_uv, dtype=np.int64))
    coords = np.array(texcoords, dtype=np.float64).reshape(-1, 2)
    coords = np.concatenate([coords, np.full((1, 2), np.nan)])
    uv = coords[np.where(corner_uv < 0, len(coords) - 1, corner_uv)]
    mesh = finish(positions, faces, table[mtl], counts, uv, mtl)
    mesh.material_names = list(names)
    return mesh


def read_ply(data):
    """Mesh of a PLY file's bytes (ascii, binary little or big endian), grey colour."""
    end = data.index(b"end_header") + len(b"end_header")
    end = data.index(b"\n", end) + 1
    header = data[:end].decode("ascii").splitlines()
    fmt = next(line.split()[1] for line in header if line.startswith("format"))
    elements = []
    for line in header:
        words = line.split()
        if words[:1] == ["element"]:
            elements.append((words[1], int(words[2]), []))
        elif words[:1] == ["property"]:
            elements[-1][2].append(words[1:])
    body = data[end:]
    if fmt == "ascii":
        values = np.array(body.split(), dtype=np.float64)
        arrays, _ = read_ply_ascii(elements, values)
    else:
        order = "<" if fmt == "binary_little_endian" else ">"
        arrays, _ = read_ply_binary(elements, body, order)
    positions = arrays["vertex"]
    faces, sizes = arrays["face"]
    tri, _ = fan(np.cumsum(sizes) - sizes, sizes, faces)
    colour = np.broadcast_to(np.array(DEFAULT_COLOUR), (len(tri), 3))
    return finish(positions, tri, colour, {"polygons": len(sizes)})


def read_ply_ascii(elements, values):
    """Vertex positions and face lists (flat, sizes) from ascii values."""
    arrays, pos = {}, 0
    for name, count, props in elements:
        if name == "face":
            flat, sizes = [], []
            for _ in range(count):
                row = []
                for prop in props:
                    if prop[0] == "list":
                        n = int(values[pos])
                        row = values[pos + 1 : pos + 1 + n].astype(np.int64)
                        pos += 1 + n
                    else:
                        pos += 1
                flat.append(row)
                sizes.append(len(row))
            arrays["face"] = (np.concatenate(flat), np.array(sizes))
        else:
            width = len(props)
            block = values[pos : pos + count * width].reshape(count, width)
            pos += count * width
            if name == "vertex":
                cols = [p[-1] for p in props]
                arrays["vertex"] = block[:, [cols.index(k) for k in "xyz"]]
    return arrays, pos


def read_ply_binary(elements, body, order):
    """Vertex positions and face lists (flat, sizes) from binary data."""
    arrays, pos = {}, 0
    for name, count, props in elements:
        lists = [p for p in props if p[0] == "list"]
        if not lists:
            dtype = np.dtype([(p[-1], order + PLY_TYPES[p[0]]) for p in props])
            block = np.frombuffer(body, dtype=dtype, count=count, offset=pos)
            pos += count * dtype.itemsize
            if name == "vertex":
                arrays["vertex"] = np.stack(
                    [block[k].astype(np.float64) for k in "xyz"], axis=1
                )
            continue
        arrays[name], pos = read_ply_lists(props, count, body, pos, order)
    return arrays, pos


def read_ply_lists(props, count, body, pos, order):
    """Face lists of one element with fixed fields before a single list property."""
    head = [p for p in props if p[0] != "list"]
    lst = next(p for p in props if p[0] == "list")
    count_t, item_t = np.dtype(order + PLY_TYPES[lst[1]]), np.dtype(
        order + PLY_TYPES[lst[2]]
    )
    skip = sum(np.dtype(PLY_TYPES[p[0]]).itemsize for p in head)
    n = int(np.frombuffer(body, count_t, 1, pos + skip)[0])
    row = np.dtype([("head", "u1", (skip,)), ("n", count_t), ("ids", item_t, (n,))])
    block = np.frombuffer(body, row, count, pos) if count else None
    if count and (block["n"] == n).all():
        sizes = np.full(count, n)
        return (
            block["ids"].astype(np.int64).ravel(),
            sizes,
        ), pos + count * row.itemsize
    flat, sizes = [], []
    for _ in range(count):
        pos += skip
        k = int(np.frombuffer(body, count_t, 1, pos)[0])
        pos += count_t.itemsize
        flat.append(np.frombuffer(body, item_t, k, pos).astype(np.int64))
        pos += k * item_t.itemsize
        sizes.append(k)
    return (np.concatenate(flat), np.array(sizes)), pos


def read_member(archive, member):
    """Bytes of one file: inside a .zip or .tar(.gz) archive, or a (gzipped) file."""
    archive = Path(archive)
    name = archive.name
    if name.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            return z.read(member)
    if name.endswith((".tar.gz", ".tgz", ".tar")):
        with tarfile.open(archive) as t:
            return t.extractfile(member).read()
    if name.endswith(".gz"):
        return gzip.decompress(archive.read_bytes())
    return archive.read_bytes()


def find_mtl(obj_text):
    """The MTL file names an OBJ file's text asks for."""
    return [m.strip() for m in re.findall(r"^mtllib\s+(.+)$", obj_text, re.MULTILINE)]


def read_obj_in(archive, member, colours=None, with_uv=False):
    """Mesh of an OBJ file and the MTL files it names (same folder); `colours`
    replaces the diffuse colour of the materials it names."""
    text = read_member(archive, member).decode("latin-1")
    folder = member.rsplit("/", 1)[0] + "/" if "/" in member else ""
    materials, statements = {}, {}
    for mtl in find_mtl(text):
        mtl_text = read_member(archive, folder + mtl).decode("latin-1")
        materials.update(parse_mtl(mtl_text))
        statements.update(parse_statements(mtl_text))
    materials.update({k: tuple(v) for k, v in (colours or {}).items()})
    mesh = parse_obj(text, materials, with_uv)
    if with_uv:
        mesh.statements = statements
    return mesh


def read_mesh(archive, member, colours=None, with_uv=False):
    """Mesh of an OBJ or PLY file, given as an archive and its member (or the file);
    with_uv: an OBJ's texture coordinates and materials too (a PLY's uv stays None)."""
    if member.lower().endswith(".obj"):
        return read_obj_in(archive, member, colours, with_uv)
    return read_ply(read_member(archive, member))
