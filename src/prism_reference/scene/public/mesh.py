"""A public scene's mesh: read from its downloads, a ground added, colours shaded, the
converted file written and read."""

import json

import numpy as np

from prism_reference.scene.importers import meshio, tungsten
from prism_reference.scene.public.table import fetch, public_dir, table

GROUND_CELLS = 16
GROUND_TINT = ((0.55, 0.55, 0.52), (0.42, 0.42, 0.40))
# Baked shade: colour = diffuse * (SHADE_BASE + SHADE_GAIN * |normal . SHADE_DIR|).
SHADE_BASE, SHADE_GAIN = 0.55, 0.45
SHADE_DIR = np.array([0.3, 1.0, 0.5]) / np.sqrt(0.09 + 1.0 + 0.25)


def ground(lo, hi, extent):
    """A checkered grid of GROUND_CELLS^2 squares at the height of lo, under lo..hi."""
    centre = (lo + hi) / 2
    half = extent * max(hi[0] - lo[0], hi[2] - lo[2])
    s = np.linspace(-half, half, GROUND_CELLS + 1)
    i, j = np.meshgrid(np.arange(GROUND_CELLS), np.arange(GROUND_CELLS), indexing="ij")
    i, j = i.ravel(), j.ravel()
    y = np.full(len(i), lo[1])
    corners = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
    pos = np.stack(
        [np.stack([centre[0] + s[a], y, centre[2] + s[b]], 1) for a, b in corners], 1
    ).reshape(-1, 3)
    quad = 4 * np.arange(len(i))[:, None]
    faces = np.concatenate([quad + [0, 2, 1], quad + [0, 3, 2]])
    tint = np.array(GROUND_TINT)[(i + j) % 2]
    return pos, faces, np.concatenate([tint, tint])


def colour_ranks(colour):
    """Per triangle the rank of its colour (T, 3) among the distinct colours in
    lexicographic order, and their count; equal neighbours are ranked once."""
    if len(colour) == 0:
        return np.zeros(0, dtype=np.int64), 0
    starts = np.flatnonzero(np.any(colour[1:] != colour[:-1], axis=1)) + 1
    starts = np.concatenate([[0], starts])
    distinct, inverse = np.unique(colour[starts], axis=0, return_inverse=True)
    sizes = np.diff(np.append(starts, len(colour)))
    return np.repeat(inverse.reshape(-1), sizes), len(distinct)


def shared_vertices(positions, faces, colour):
    """Vertices split by (vertex, colour), so each triangle keeps its flat colour: the
    distinct (vertex, colour rank) pairs in order, each triangle's corners among them.
    """
    rank, count = colour_ranks(colour)
    vertex = faces.reshape(-1).astype(np.int64)
    corner_rank = np.repeat(rank, 3)
    low = np.full(len(positions), count, dtype=np.int64)
    high = np.full(len(positions), -1, dtype=np.int64)
    np.minimum.at(low, vertex, corner_rank)
    np.maximum.at(high, vertex, corner_rank)
    mixed = (high >= 0) & (low != high)
    pick = mixed[vertex]
    keys = vertex[pick] * count + corner_rank[pick]
    pairs = np.unique(keys)
    per = (high >= 0).astype(np.int64)
    per[mixed] = 0
    np.add.at(per, pairs // max(count, 1), 1)
    first = np.cumsum(per) - per
    inverse = first[vertex]
    own = vertex[pick] * count
    inverse[pick] += np.searchsorted(pairs, keys) - np.searchsorted(pairs, own)
    corner = np.empty(int(per.sum()), dtype=np.int64)
    corner[inverse] = np.arange(len(inverse))
    return (
        positions[np.repeat(np.arange(len(positions)), per)],
        colour[corner // 3].astype(np.float64),
        inverse.reshape(-1, 3),
    )


def vertex_shade(positions, faces):
    """Per-vertex shade: area-weighted mean over its triangles of a fixed-light term."""
    p = positions[faces]
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    area = np.sqrt((n * n).sum(axis=1))
    shade = SHADE_BASE + SHADE_GAIN * np.abs(n @ SHADE_DIR) / np.maximum(area, 1e-300)
    total = np.bincount(faces.ravel(), np.repeat(area * shade, 3), len(positions))
    weight = np.bincount(faces.ravel(), np.repeat(area, 3), len(positions))
    return np.where(weight > 0, total / np.maximum(weight, 1e-300), 1.0)


def read_parts(name, data, with_uv=False):
    """Positions, faces, colours and counts of a scene's meshes (ground added), and
    the meshes as read (with texture coordinates and materials when with_uv)."""
    entry = table()[name]
    paths = fetch(name, data)
    by_name = {p.name: p for p in paths}
    pos, faces, colour, counts, meshes = [], [], [], {}, []
    offset = 0
    for part in entry["meshes"]:
        path = by_name[part["file"]]
        colours = part.get("material_colours")
        if part["member"].lower().endswith(".json"):
            mesh = tungsten.read_scene(
                path, part["member"], colours, with_uv, part.get("inside")
            )
        else:
            mesh = meshio.read_mesh(path, part["member"], colours, with_uv)
        meshes.append(mesh)
        p = mesh.positions @ np.array(entry.get("axes", np.eye(3))).T
        c = mesh.colour
        if "colour" in part:
            c = np.broadcast_to(np.array(part["colour"], dtype=np.float64), c.shape)
        pos.append(p)
        faces.append(mesh.faces + offset)
        colour.append(c)
        offset += len(p)
        for k, v in mesh.counts.items():
            counts[k] = counts.get(k, 0) + v
    pos, faces = np.concatenate(pos), np.concatenate(faces)
    colour = np.concatenate(colour)
    if entry.get("ground"):
        lo, hi = pos[faces].reshape(-1, 3).min(0), pos[faces].reshape(-1, 3).max(0)
        gp, gf, gc = ground(lo, hi, entry["ground"])
        pos, faces = np.concatenate([pos, gp]), np.concatenate([faces, gf + len(pos)])
        colour = np.concatenate([colour, gc])
        counts["ground_triangles"] = len(gf)
    return pos, faces, colour, counts, meshes


def convert(name, data):
    """Reads a scene's mesh from its downloads and saves it as <public>/<name>.npz."""
    pos, faces, colour, counts, _ = read_parts(name, data)
    vp, vc, idx = shared_vertices(pos, faces, colour)
    vc = vc * vertex_shade(vp, idx)[:, None]
    counts["triangles_total"], counts["vertices"] = len(idx), len(vp)
    out = public_dir(data) / f"{name}.npz"
    np.savez(
        out,
        positions=vp.astype(np.float32),
        colors=np.clip(vc, 0, 1).astype(np.float32),
        indices=idx.astype(np.int32),
        counts=json.dumps(counts),
    )
    return out


def load_mesh(name, data):
    """The converted mesh of a scene; missing, it is an error (nothing downloads)."""
    path = public_dir(data) / f"{name}.npz"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing; fetch it with: "
            f"python scripts/data/public_scenes.py fetch {name}"
        )
    with np.load(path) as f:
        return {k: f[k] for k in ("positions", "colors", "indices")}, json.loads(
            str(f["counts"])
        )
