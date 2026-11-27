"""Round trips: the check's own files written, loaded, and every value compared with what
was written; then a sidecar and an instance table, and `flatten` against numpy."""

import json

import numpy as np

from checks.scene_description import build
from checks.scene_description.compare import same
from prism_reference.scene.artist.entry import view_of
from prism_reference.scene.description.check import check
from prism_reference.scene.description.flatten import flatten
from prism_reference.scene.description.report import coverage
from prism_reference.scene.importers.gltf import load
from prism_reference.scene.importers.gltf.accessors import read
from prism_reference.scene.importers.gltf.container import open_container

ORDER = ["root", "child", "grandchild", "copies", "sun", "lamp", "spot", "cam_persp"]
ORDER += ["cam_ortho", "animated", "rider", "skinned", "mirror"]
MOVING = {"animated", "rider", "skinned"}


def rodrigues(axis, angle):
    """The 3 x 3 rotation by `angle` about `axis`."""
    k = np.asarray(axis, np.float64) / np.linalg.norm(axis)
    cross = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(angle) * cross + (1 - np.cos(angle)) * cross @ cross


def trs(t=(0, 0, 0), axis=(0, 0, 1), angle=0.0, s=(1, 1, 1)):
    """The 4 x 4 matrix T @ R @ S."""
    m = np.eye(4)
    m[:3, :3] = rodrigues(axis, angle) @ np.diag(s)
    m[:3, 3] = t
    return m


def expected_worlds():
    """World matrices of the named nodes and the instanced copies, by numpy's product."""
    root = trs(build.ROOT_TRS["translation"], (0, 1, 0), 0.5, build.ROOT_TRS["scale"])
    child = root @ np.array(build.CHILD_MATRIX, np.float64).reshape(4, 4).T
    copies = root @ trs((0, 1, 0))
    worlds = {
        "root": root,
        "child": child,
        "grandchild": child @ trs(s=(1, 1, 3)),
        "copies": copies,
        "mirror": root @ trs(s=(-1, 1, 1)),
        "animated": root,
    }
    copies_each = [copies @ trs(t, a, g, s) for t, a, g, s in build.INSTANCES]
    return worlds, np.array(copies_each)


def _accessors(name, path):
    """Every raw accessor against the values written, normalized ones by glTF's rule."""
    _, _, raw = build.document()
    container = open_container(path)
    for (component, kind, norm, values), index in zip(build.RAW, raw):
        want = values
        if norm:
            top = np.float64(np.iinfo(values.dtype).max)
            want = np.maximum(values / top, -1.0).astype(np.float32)
        same(f"{name} accessor {component} {kind}", read(container, index), want)
    for case, index in zip(build.SPARSE, raw[len(build.RAW) :]):
        component, kind, base, count, _, rows, values = case
        want = np.zeros(count, values.dtype) if base is None else base.copy()
        want[rows] = values
        what = "without" if base is None else "with"
        got = read(container, index)
        same(f"{name} sparse accessor {what} a base view", got, want)
        same(
            f"{name} sparse accessor {what} a base view is new",
            got.flags.writeable,
            True,
        )


def _meshes(name, scene):
    """Mesh primitives and their attributes, carried arrays and zero-copy views."""
    v = build.VALUES
    a, b, c = scene.meshes[0].primitives
    same(f"{name} quad primitives (mode 3 dropped)", len(scene.meshes[0].primitives), 3)
    for key in ("positions", "normals", "tangents", "uv0"):
        same(f"{name} quad {key}", getattr(a, key), v[key])
    same(
        f"{name} quad uv1 normalized u16",
        a.uv1,
        (v["uv1_raw"] / 65535.0).astype(np.float32),
    )
    same(
        f"{name} quad colors normalized u8",
        a.colors,
        (v["colors_raw"] / 255.0).astype(np.float32),
    )
    same(f"{name} quad joints carried", a.carried["JOINTS_0"], v["joints"])
    same(f"{name} quad weights carried", a.carried["WEIGHTS_0"], v["weights"])
    same(
        f"{name} quad morph target carried",
        a.carried["targets"][0]["POSITION"],
        v["target"],
    )
    same(f"{name} quad u8 indices", a.indices, v["indices_a"].astype(np.uint32))
    same(f"{name} quad material", a.material, 0)
    same(f"{name} strided positions are a view", bool(a.positions.flags.owndata), False)
    same(f"{name} u16 indices", b.indices, v["indices_b"].astype(np.uint32))
    want_b = np.concatenate([v["colors_b"], np.ones((4, 1), np.float32)], 1)
    same(f"{name} VEC3 colors get alpha 1", b.colors, want_b)
    same(f"{name} absent normals", b.normals, None)
    same(f"{name} unindexed positions", c.positions, v["unindexed"])
    same(
        f"{name} unindexed indices",
        c.indices,
        np.arange(6, dtype=np.uint32).reshape(2, 3),
    )
    same(f"{name} no material", c.material, -1)
    tri = scene.meshes[1].primitives[0]
    same(f"{name} u32 indices", tri.indices, v["tri_indices"])
    same(f"{name} u32 indices are a view", bool(tri.indices.flags.owndata), False)
    same(f"{name} index dtype", str(tri.indices.dtype), "uint32")


def _nodes(name, scene):
    """Names, parents, world matrices, moving, held indices and instances."""
    nodes = scene.nodes
    same(f"{name} node order", [n.name for n in nodes], ORDER)
    index = {n.name: i for i, n in enumerate(nodes)}
    parents = {
        "child": "root",
        "grandchild": "child",
        "rider": "animated",
        "root": None,
    }
    for child, parent in parents.items():
        same(
            f"{name} parent of {child}",
            nodes[index[child]].parent,
            -1 if parent is None else index[parent],
        )
    worlds, copies = expected_worlds()
    for key, matrix in worlds.items():
        same(f"{name} world of {key}", nodes[index[key]].world, matrix)
    same(
        f"{name} instances", nodes[index["copies"]].instances, copies.astype(np.float32)
    )
    same(f"{name} moving", sorted(n.name for n in nodes if n.moving), sorted(MOVING))
    held = {
        ("child", "mesh"): 0,
        ("copies", "mesh"): 1,
        ("sun", "light"): 0,
        ("lamp", "light"): 1,
    }
    held |= {
        ("spot", "light"): 2,
        ("cam_persp", "camera"): 0,
        ("cam_ortho", "camera"): 1,
    }
    for (key, what), want in held.items():
        same(f"{name} {key} {what}", getattr(nodes[index[key]], what), want)


def _use(name, use, texture, uv, offset=(0, 0), rotation=0.0, scale=(1, 1)):
    """One TextureUse against its written values."""
    same(f"{name} texture", use.texture, texture)
    same(f"{name} uv", use.uv, uv)
    same(f"{name} offset", use.offset, offset)
    same(f"{name} rotation", use.rotation, rotation)
    same(f"{name} scale", use.scale, scale)


def _materials(name, scene):
    """Every material field, textures, the sampler and the images' headers."""
    m, glass = scene.materials
    want = build.MATERIAL
    pbr = want["pbrMetallicRoughness"]
    same(f"{name} material name", m.name, want["name"])
    same(f"{name} base colour", m.base_color, pbr["baseColorFactor"])
    _use(
        f"{name} base colour texture",
        m.base_color_texture,
        0,
        0,
        (0.1, 0.2),
        0.3,
        (2, 3),
    )
    same(f"{name} metallic", m.metallic, 0.25)
    same(f"{name} roughness", m.roughness, 0.75)
    _use(f"{name} metallic roughness texture", m.metallic_roughness_texture, 1, 1)
    _use(f"{name} normal texture", m.normal_texture, 0, 0)
    same(f"{name} normal scale", m.normal_scale, 0.5)
    _use(f"{name} occlusion texture", m.occlusion_texture, 1, 0)
    same(f"{name} occlusion strength", m.occlusion_strength, 0.4)
    same(f"{name} emissive", m.emissive, want["emissiveFactor"])
    same(f"{name} emissive strength", m.emissive_strength, 5.0)
    _use(f"{name} emissive texture", m.emissive_texture, 0, 0)
    same(f"{name} alpha", (m.alpha_mode, m.alpha_cutoff), ("MASK", 0.3))
    same(f"{name} double sided, unlit", (m.double_sided, m.unlit), (True, True))
    same(
        f"{name} carried clearcoat",
        m.carried,
        {"KHR_materials_clearcoat": {"clearcoatFactor": 0.7}},
    )
    same(
        f"{name} defaults",
        (glass.alpha_mode, glass.metallic, glass.roughness, glass.unlit),
        ("BLEND", 1.0, 1.0, False),
    )
    same(
        f"{name} textures",
        [(t.image, t.sampler) for t in scene.textures],
        [(0, 0), (1, -1)],
    )
    s = scene.samplers[0]
    same(
        f"{name} sampler",
        (s.wrap_s, s.wrap_t, s.mag, s.min),
        ("CLAMP", "MIRROR", "NEAREST", "LINEAR_MIPMAP_LINEAR"),
    )
    png, jpeg = scene.images
    same(f"{name} png header", (png.mime, png.width, png.height), ("image/png", 64, 32))
    same(f"{name} png bytes", bytes(png.data[:4]), b"\x89PNG")
    same(
        f"{name} jpeg header",
        (jpeg.mime, jpeg.width, jpeg.height),
        ("image/jpeg", 40, 20),
    )
    same(f"{name} jpeg uri", jpeg.uri.endswith("tex one.jpg"), True)


def _lights_and_cameras(name, scene):
    """Each punctual light and camera against the written values."""
    sun, lamp, spot = scene.lights
    same(
        f"{name} directional",
        (sun.kind, sun.intensity, sun.range),
        ("directional", 3.0, None),
    )
    same(f"{name} directional colour", sun.color, [1.0, 0.9, 0.8])
    same(
        f"{name} point", (lamp.kind, lamp.intensity, lamp.range), ("point", 40.0, 10.0)
    )
    same(
        f"{name} spot",
        (spot.kind, spot.inner_cone, spot.outer_cone),
        ("spot", 0.2, 0.6),
    )
    same(f"{name} spot colour default", spot.color, [1, 1, 1])
    p, o = scene.cameras
    same(
        f"{name} perspective",
        (p.kind, p.yfov, p.aspect, p.znear, p.zfar),
        ("perspective", 0.8, 1.5, 0.1, 100.0),
    )
    same(
        f"{name} orthographic",
        (o.kind, o.xmag, o.ymag, o.znear, o.zfar),
        ("orthographic", 2.0, 1.5, 0.01, 50.0),
    )


def _notes(name, scene):
    """The notes of what was dropped, carried, refused and computed."""
    found = {(n.kind, n.what): n.count for n in scene.notes}
    for key, count in {
        ("dropped", "primitive mode 3"): 1,
        ("carried", "KHR_materials_clearcoat"): 1,
        ("carried", "animations"): 1,
        ("carried", "skins"): 1,
        ("refused", "KHR_materials_pbrSpecularGlossiness"): 1,
        ("dropped", "nodes outside the default scene"): 1,
        ("computed", "node world matrices"): 13,
        ("used", "KHR_texture_transform"): 1,
    }.items():
        same(f"{name} note {key}", found.get(key), count)


def _copies(name, scene, out, node_name, matrices, positions):
    """The flattened positions of each copy of one node against matrices @ positions."""
    at = 0
    for node in scene.nodes:
        if node.name == node_name:
            break
        if node.mesh != -1:
            n = 1 if node.instances is None else len(node.instances)
            at += n * sum(len(p.positions) for p in scene.meshes[node.mesh].primitives)
    for i, m in enumerate(matrices):
        want = positions @ m[:3, :3].T + m[:3, 3]
        rows = out["positions"][at + i * len(positions) : at + (i + 1) * len(positions)]
        same(f"{name} flattened {node_name} copy {i}", rows, want.astype(np.float32))


def file_case(name, path):
    """Loads one written file and compares everything; returns the scene."""
    _accessors(name, path)
    scene = load(path)
    check(scene)
    _meshes(name, scene)
    _nodes(name, scene)
    _materials(name, scene)
    _lights_and_cameras(name, scene)
    _notes(name, scene)
    report = coverage(scene)
    whole = {"scenes": 2, "nodes": 14, "instanced_nodes": 1}
    same(f"{name} whole-file counts", scene.source["file"] == whole, True)
    same(f"{name} report file instanced nodes", report["file_instanced_nodes"], 1)
    same(f"{name} stored triangles", report["stored_triangles"], build.STORED_TRIANGLES)
    same(f"{name} drawn triangles", report["drawn_triangles"], build.DRAWN_TRIANGLES)
    out = flatten(scene, 1000)
    same(f"{name} flatten triangles", len(out["indices"]), build.DRAWN_TRIANGLES)
    _, copies = expected_worlds()
    _copies(name, scene, out, "copies", copies, build.VALUES["tri"].astype(np.float64))
    mirror = next(i for i, n in enumerate(scene.nodes) if n.name == "mirror")
    same(
        f"{name} mirror winding flipped",
        out["indices"][-1] - out["indices"][-1].min(),
        [0, 2, 1],
    )
    same(f"{name} mirror node index", mirror, len(scene.nodes) - 1)
    return scene


SIDECAR = {
    "version": 1,
    "source": {"file": "quad.blend", "blender": "4.2", "frame": 1},
    "render": {
        "size": [640, 360],
        "camera": "cam_persp",
        "shift": [0.1, -0.05],
        "sensor_fit": "HORIZONTAL",
        "exposure": 0.5,
        "view_transform": "AgX",
        "look": "None",
        "gamma": 1.0,
    },
    "world": {
        "color": [0.05, 0.06, 0.07],
        "strength": 1.5,
        "environment": "sky.hdr",
        "rotation": [0, 0.5, 0],
    },
    "area_lights": [
        {
            "name": "panel",
            "shape": "RECTANGLE",
            "size": [2.0, 1.0],
            "color": [1, 0.9, 0.8],
            "power": 150.0,
            "matrix": [1, 0, 0, 0, 0, 1, 0, 3, 0, 0, 1, 0, 0, 0, 0, 1],
        }
    ],
    "instances": {"file": "quad.instances.npz"},
    "not_exported": {
        "materials": ["toon"],
        "lights": ["sky light"],
        "objects": [
            "hair",
            {"name": "smoke", "type": "VOLUME", "reason": "type not copied"},
        ],
    },
}


def table_matrices():
    """The instance table's matrices for the node `grandchild`."""
    return np.array(
        [trs((1, 2, 3)), trs((0, 0, -5), (1, 0, 0), 1.2, (2, 2, 2))], np.float32
    )


def write_sidecar(path, sidecar=SIDECAR, names=("grandchild",)):
    """Writes `<stem>.prism.json` and `<stem>.instances.npz` beside `path`."""
    doc = json.loads(json.dumps(sidecar))
    doc["instances"] = {"file": path.stem + ".instances.npz"}
    path.with_name(path.stem + ".prism.json").write_text(json.dumps(doc))
    matrices = table_matrices()
    np.savez(
        path.with_name(path.stem + ".instances.npz"),
        node_names=np.array(names),
        starts=np.array([0, len(matrices)], np.int64),
        matrices=matrices,
    )


def sidecar_case(name, path):
    """The sidecar and the instance table applied, and flatten with the table's copies."""
    write_sidecar(path)
    scene = load(path)
    check(scene)
    index = {n.name: i for i, n in enumerate(scene.nodes)}
    r = scene.render
    same(
        f"{name} render",
        (r.camera, r.exposure, r.view_transform, r.look, r.gamma),
        (index["cam_persp"], 0.5, "AgX", "None", 1.0),
    )
    same(f"{name} render size", r.size, [640, 360])
    p, o = scene.cameras
    same(
        f"{name} render camera shift, sensor fit",
        (p.shift_x, p.shift_y, p.sensor_fit, o.shift_x, o.shift_y, o.sensor_fit),
        (0.1, -0.05, "HORIZONTAL", 0.0, 0.0, ""),
    )
    views, _, notes = view_of(scene)
    same(f"{name} view shift", views["camera"]["shift"], [0.1, -0.05])
    same(
        f"{name} no camera shift note",
        [n for n in notes if n.what == "camera shift"],
        [],
    )
    w = scene.world
    same(f"{name} world", (w.strength, w.environment), (1.5, "sky.hdr"))
    same(
        f"{name} world colour, rotation",
        np.concatenate([w.color, w.rotation]),
        [0.05, 0.06, 0.07, 0, 0.5, 0],
    )
    area, node = scene.lights[-1], scene.nodes[-1]
    same(
        f"{name} area light",
        (area.kind, area.intensity, area.shape),
        ("area", 150.0, "RECTANGLE"),
    )
    same(
        f"{name} area light size, colour",
        np.concatenate([area.size, area.color]),
        [2, 1, 1, 0.9, 0.8],
    )
    same(
        f"{name} area light node",
        (node.name, node.parent, node.light),
        ("panel", -1, len(scene.lights) - 1),
    )
    same(
        f"{name} area light matrix",
        node.world,
        np.array(SIDECAR["area_lights"][0]["matrix"]).reshape(4, 4),
    )
    same(
        f"{name} table instances",
        scene.nodes[index["grandchild"]].instances,
        table_matrices(),
    )
    dropped = sorted(
        n.detail
        for n in scene.notes
        if n.kind == "dropped" and n.what.endswith("not exported")
    )
    same(
        f"{name} not exported",
        dropped,
        sorted(["toon", "sky light", "hair", "smoke: type not copied"]),
    )
    out = flatten(scene, 1000)
    same(
        f"{name} flatten triangles with the table",
        len(out["indices"]),
        build.DRAWN_TRIANGLES + 1,
    )
    _copies(
        name,
        scene,
        out,
        "grandchild",
        table_matrices().astype(np.float64),
        build.VALUES["tri"].astype(np.float64),
    )
