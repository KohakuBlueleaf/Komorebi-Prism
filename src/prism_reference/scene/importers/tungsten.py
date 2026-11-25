"""Tungsten scenes (`scene.json`, `.wo3` or `.obj` meshes) as one mesh of meshio's
layout, each BSDF as MTL statements read like an OBJ material."""

import json

import numpy as np

from prism_reference.scene.importers import meshio

DISK_SEGMENTS = 32
SPHERE_RINGS, SPHERE_SEGMENTS = 12, 24
PLASTIC_SPECULAR = 0.04  # specular colour of a plastic's coat
CONDUCTOR_COLOUR = 0.6  # a conductor's albedo factor
CONDUCTOR_SPECULAR = 0.9
GLASS_TRANSMISSION = 0.92  # a dielectric's transmission
MEDIUM_DEPTH = 0.005  # path through a tinted glass's medium
EXPONENT_MAX = 1024


def read_wo3(data):
    """Positions, normals (V, 3), uv (V, 2) and triangles (T, 3) of a `.wo3` file's
    bytes: a uint64 count and that many vertices (position, normal, uv as float32),
    then a uint64 count and that many triangles (3 uint32, a material)."""
    count = int(np.frombuffer(data, np.uint64, 1, 0)[0])
    vertex = np.frombuffer(data, np.float32, count * 8, 8).reshape(count, 8)
    start = 8 + 32 * count
    tris = int(np.frombuffer(data, np.uint64, 1, start)[0])
    if start + 8 + 16 * tris != len(data):
        raise ValueError(f"not a .wo3 file: {len(data)} bytes, {count} vertices")
    faces = np.frombuffer(data, np.uint32, tris * 4, start + 8).reshape(tris, 4)
    return (
        vertex[:, 0:3].astype(np.float64),
        vertex[:, 3:6].astype(np.float64),
        vertex[:, 6:8].astype(np.float64),
        faces[:, :3].astype(np.int64),
    )


def facing(positions, normals, faces):
    """Triangles turned where their winding disagrees with their corners' normals (a
    .wo3 file's winding is not always outward; Tungsten draws both sides)."""
    p = positions[faces]
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    back = np.einsum("ij,ij->i", n, normals[faces].sum(1)) < 0
    return np.where(back[:, None], faces[:, ::-1], faces)


def vector(value, default):
    """A number or a list of three as (3,) float64; None gives default."""
    if value is None:
        value = default
    return np.broadcast_to(np.asarray(value, dtype=np.float64), 3).copy()


def rotation_yxz(degrees):
    """Tungsten's `Mat4f::rotYXZ`: rotations about z, then x, then y (degrees)."""
    x, y, z = np.radians(degrees)
    rz = np.array([[np.cos(z), -np.sin(z), 0], [np.sin(z), np.cos(z), 0], [0, 0, 1]])
    rx = np.array([[1, 0, 0], [0, np.cos(x), -np.sin(x)], [0, np.sin(x), np.cos(x)]])
    ry = np.array([[np.cos(y), 0, np.sin(y)], [0, 1, 0], [-np.sin(y), 0, np.cos(y)]])
    return ry @ rx @ rz


def transform(spec):
    """The 4 x 4 matrix of a primitive's `transform`: translate, rotate (YXZ), scale."""
    spec = spec or {}
    m = np.eye(4)
    m[:3, :3] = rotation_yxz(vector(spec.get("rotation"), 0.0)) * vector(
        spec.get("scale"), 1.0
    )
    m[:3, 3] = vector(spec.get("position"), 0.0)
    return m


def camera(scene):
    """(eye, target, field of view in degrees) of a scene's pinhole camera."""
    spec = scene["camera"]["transform"]
    eye = vector(spec["position"], 0.0)
    return eye, vector(spec["look_at"], 0.0), float(scene["camera"]["fov"])


def unit_shape(kind):
    """Positions and triangles of a primitive in its own frame, facing +y: a quad of
    side 1, a disk of radius 1 (DISK_SEGMENTS), a sphere of radius 1 (outward)."""
    if kind == "quad":
        p = np.array([[-0.5, 0, -0.5], [0.5, 0, -0.5], [0.5, 0, 0.5], [-0.5, 0, 0.5]])
        return p, np.array([[0, 2, 1], [0, 3, 2]])
    if kind == "disk":
        a = 2 * np.pi * np.arange(DISK_SEGMENTS) / DISK_SEGMENTS
        rim = np.stack([np.cos(a), np.zeros_like(a), np.sin(a)], 1)
        k = np.arange(DISK_SEGMENTS)
        faces = np.stack([np.zeros_like(k), (k + 1) % DISK_SEGMENTS + 1, k + 1], 1)
        return np.concatenate([[[0.0, 0.0, 0.0]], rim]), faces
    theta = np.pi * np.arange(SPHERE_RINGS + 1) / SPHERE_RINGS
    phi = 2 * np.pi * np.arange(SPHERE_SEGMENTS) / SPHERE_SEGMENTS
    t, f = np.meshgrid(theta, phi, indexing="ij")
    p = np.stack([np.sin(t) * np.cos(f), np.cos(t), np.sin(t) * np.sin(f)], -1)
    i, j = np.meshgrid(
        np.arange(SPHERE_RINGS), np.arange(SPHERE_SEGMENTS), indexing="ij"
    )
    a = i * SPHERE_SEGMENTS + j
    b = i * SPHERE_SEGMENTS + (j + 1) % SPHERE_SEGMENTS
    c, d = a + SPHERE_SEGMENTS, b + SPHERE_SEGMENTS
    faces = np.concatenate([np.stack([a, b, d], -1), np.stack([a, d, c], -1)])
    return p.reshape(-1, 3), faces.reshape(-1, 3)


def area(positions, faces):
    """The summed area of triangles."""
    p = positions[faces]
    return (
        0.5
        * np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1).sum()
    )


def exponent(roughness):
    """A Phong exponent of a microfacet roughness: 2 / r^2 - 2, 1 to EXPONENT_MAX."""
    r = max(float(roughness), 1e-3)
    return float(np.clip(2.0 / (r * r) - 2.0, 1.0, EXPONENT_MAX))


def words(colour):
    """Three numbers as an MTL statement's text."""
    return " ".join(f"{float(v):.6g}" for v in colour)


def bsdf_statements(bsdf):
    """MTL statements of a Tungsten BSDF and whether its type was mapped. Colour or
    texture to `Kd` / `map_Kd`; plastic adds a specular coat; a conductor is a plain
    colour with a specular term; a dielectric is transparent (`Tr`); unknown: grey."""
    kind = bsdf.get("type", "lambert")
    albedo = bsdf.get("albedo", 1.0)
    out = {}
    if isinstance(albedo, str):
        out["map_Kd"], colour = albedo, (1.0, 1.0, 1.0)
    elif isinstance(albedo, dict):
        colour = meshio.DEFAULT_COLOUR
        if albedo.get("type") == "bitmap" and "file" in albedo:
            out["map_Kd"], colour = albedo["file"], (1.0, 1.0, 1.0)
    else:
        colour = vector(albedo, 1.0)
    mapped = True
    if kind in ("lambert", "oren_nayar"):
        pass
    elif kind in ("plastic", "rough_plastic"):
        out["Ks"] = words([PLASTIC_SPECULAR] * 3)
        out["Ns"] = f"{exponent(bsdf.get('roughness', 0.0)):.6g}"
    elif kind in ("conductor", "rough_conductor"):
        colour = np.asarray(colour) * CONDUCTOR_COLOUR
        out["Ks"] = words([CONDUCTOR_SPECULAR] * 3)
        out["Ns"] = f"{exponent(bsdf.get('roughness', 0.0)):.6g}"
    elif kind in ("dielectric", "rough_dielectric", "thinsheet"):
        out["Tr"] = f"{GLASS_TRANSMISSION * float(np.mean(colour)):.6g}"
        out["Ks"] = words([PLASTIC_SPECULAR] * 3)
    elif kind == "null":
        colour = (0.0, 0.0, 0.0)
    else:
        colour, mapped = meshio.DEFAULT_COLOUR, False
    out["Kd"] = words(colour)
    return out, mapped


def tinted(statements, medium):
    """Glass statements with the colour of the medium inside it: transmission
    GLASS_TRANSMISSION exp(-sigma_a density MEDIUM_DEPTH) per channel (`Tf` = 1 - it),
    and that colour, scaled to a largest channel of 1, as `Kd`."""
    sigma = vector(medium.get("sigma_a"), 0.0) * float(medium.get("density", 1.0))
    tau = GLASS_TRANSMISSION * np.exp(-sigma * MEDIUM_DEPTH)
    out = {k: v for k, v in statements.items() if k != "Tr"}
    return out | {"Tf": words(1.0 - tau), "Kd": words(tau / tau.max())}


def primitive_shape(prim, archive, folder):
    """World positions, corner uv (T, 3, 2) and triangles of one primitive, None for
    a kind that is not read (curves, infinite lights); triangles face as Tungsten's."""
    kind = prim["type"]
    if kind == "mesh":
        data = meshio.read_member(archive, folder + prim["file"])
        if prim["file"].lower().endswith(".wo3"):
            p, normals, uv, faces = read_wo3(data)
            faces = facing(p, normals, faces)
            uv = uv[faces]
        else:
            mesh = meshio.parse_obj(data.decode("latin-1"), {}, with_uv=True)
            p, faces, uv = mesh.positions, mesh.faces, mesh.uv
    elif kind in ("quad", "disk", "sphere"):
        p, faces = unit_shape(kind)
        uv = np.zeros((len(faces), 3, 2))
    else:
        return None
    m = transform(prim.get("transform"))
    world = p @ m[:3, :3].T + m[:3, 3]
    if np.linalg.det(m[:3, :3]) < 0:
        faces, uv = faces[:, ::-1], uv[:, ::-1]
    return world, uv, faces


def emission(prim, positions, faces):
    """A primitive's emitted radiance (3,): `emission`, or `power` over pi x its area;
    None when it emits nothing."""
    if "emission" in prim:
        return vector(prim["emission"], 0.0)
    if "power" in prim:
        return vector(prim["power"], 0.0) / (np.pi * area(positions, faces))
    return None


def read_scene(archive, member, colours=None, with_uv=False, inside=None):
    """Mesh (meshio layout) of a Tungsten `scene.json`; `colours` replaces the diffuse
    colour of the materials it names; `inside` ({"point", "materials"}) turns those
    materials' triangles to face the point."""
    scene = json.loads(meshio.read_member(archive, member))
    folder = member.rsplit("/", 1)[0] + "/" if "/" in member else ""
    statements, mapped = {}, {}
    for bsdf in scene.get("bsdfs", []):
        statements[bsdf["name"]], mapped[bsdf["name"]] = bsdf_statements(bsdf)
    media = {m["name"]: m for m in scene.get("media", [])}
    names, parts, counts = {}, [], {"unmapped_bsdfs": 0, "emitters": 0}
    offset = 0
    for k, prim in enumerate(scene["primitives"]):
        shape = primitive_shape(prim, archive, folder)
        if shape is None:
            key = f"skipped_{prim['type']}"
            counts[key] = counts.get(key, 0) + 1
            continue
        p, uv, faces = shape
        name, glow = prim.get("bsdf"), emission(prim, p, faces)
        if not isinstance(name, str):
            name = f"{prim['type']}_{k}"
            statements[name], mapped[name] = bsdf_statements(prim.get("bsdf") or {})
        medium = media.get(prim.get("int_medium"))
        if medium is not None and "Tr" in statements[name]:
            glass, name = name, f"{name}+{prim['int_medium']}"
            statements[name], mapped[name] = tinted(statements[glass], medium), True
        if glow is not None and glow.max() > 0:
            name = f"emitter_{k}"
            statements[name] = {"Kd": "0 0 0", "Ke": words(glow)}
            mapped[name] = True
            counts["emitters"] += 1
        if not mapped[name] and name not in names:
            counts["unmapped_bsdfs"] += 1
        parts.append((p, uv, faces + offset, names.setdefault(name, len(names))))
        offset += len(p)
    positions = np.concatenate([q[0] for q in parts])
    uv_all = np.concatenate([q[1] for q in parts])
    faces = np.concatenate([q[2] for q in parts])
    material = np.concatenate([np.full(len(q[2]), q[3]) for q in parts])
    if inside:
        turn = np.isin(material, [names[n] for n in inside["materials"]])
        p = positions[faces]
        n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
        turn &= np.einsum("ij,ij->i", n, np.asarray(inside["point"]) - p.mean(1)) < 0
        faces = np.where(turn[:, None], faces[:, ::-1], faces)
        uv_all = np.where(turn[:, None, None], uv_all[:, ::-1], uv_all)
        counts["turned_inside"] = int(turn.sum())
    table = np.array([meshio.DEFAULT_COLOUR] * (len(names) + 1), dtype=np.float64)
    for name, k in names.items():
        own = (colours or {}).get(name)
        table[k] = (
            own
            if own is not None
            else vector([float(w) for w in statements[name]["Kd"].split()], 0.0)
        )
    counts |= {"primitives": len(parts), "materials": len(names)}
    if not with_uv:
        return meshio.finish(positions, faces, table[material], counts)
    mesh = meshio.finish(positions, faces, table[material], counts, uv_all, material)
    mesh.material_names = list(names)
    mesh.statements = {name: statements[name] for name in names}
    return mesh
