"""Run inside Blender: the open scene as a .glb (one node a geometry key), its sidecar
JSON, its instance table and the world's map.
`blender --background <file.blend> --python export.py -- <out_stem> [--frame N]`"""

import argparse
import json
import os
import shutil
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import common
import materials
import numpy

PUNCTUAL = {"SUN", "POINT", "SPOT"}
NAMES_LISTED = 200
TRIANGLES_MODE = 4
RENDER_SIZE = (
    "resolution_x",
    "resolution_y",
    "resolution_percentage",
    "pixel_aspect_x",
    "pixel_aspect_y",
)


def named_copy(name, data):
    """A new object of `data` carrying `name`: a local object holding that name is
    renamed out of the way first (the .blend is never saved)."""
    holder = bpy.data.objects.get(name)
    if holder is not None and holder.library is None:
        holder.name = f"prism_source_{len(bpy.data.objects)}"
    copy = bpy.data.objects.new(name, data)
    copy.name = name
    return copy


def build_scene(found, depsgraph, source):
    """A new scene: one object a key at the identity, the cameras and punctual lights,
    at the source's render size (the cameras' field of view is written for it)."""
    scene = bpy.data.scenes.new("prism_export")
    for name in RENDER_SIZE:
        setattr(scene.render, name, getattr(source.render, name))
    names = []
    for i, key in enumerate(sorted(found)):
        name = f"prism_mesh_{i:06d}"
        obj = bpy.data.objects.new(name, found[key]["source"])
        scene.collection.objects.link(obj)
        names.append(obj.name)
    for obj in source.objects:
        if obj.type == "CAMERA":
            matrix = obj.evaluated_get(depsgraph).matrix_world.copy()
            copy = named_copy(obj.name, obj.data)
            copy.matrix_world = matrix
            scene.collection.objects.link(copy)
    for name, data, matrix in common.lights(depsgraph):
        if data.type in PUNCTUAL:
            copy = named_copy(name, data)
            copy.matrix_world = matrix
            scene.collection.objects.link(copy)
    return scene, names


def table(found, names, path):
    """Writes the instance table: node names, starts, glTF matrices."""
    keys = sorted(found)
    counts = [len(found[k]["matrices"]) for k in keys]
    starts = numpy.concatenate([[0], numpy.cumsum(counts)]).astype(numpy.int64)
    matrices = numpy.zeros((int(starts[-1]), 4, 4), dtype=numpy.float32)
    for i, key in enumerate(keys):
        for j, matrix in enumerate(found[key]["matrices"]):
            matrices[starts[i] + j] = common.to_gltf(matrix)
    numpy.savez(path, node_names=numpy.array(names), starts=starts, matrices=matrices)


def socket_source(socket, kind):
    """The node of `kind` linked straight into `socket`, or None."""
    if socket.is_linked and socket.links[0].from_node.bl_idname == kind:
        return socket.links[0].from_node
    return None


def world(scene, stem, not_exported):
    """The sidecar's world; saves an environment map beside the stem."""
    entry = {"color": [0.0, 0.0, 0.0], "strength": 1.0, "environment": None}
    entry["rotation"] = [0.0, 0.0, 0.0]
    w = scene.world
    output = common.output_node(w.node_tree) if w and w.use_nodes else None
    surface = output.inputs.get("Surface") if output else None
    background = socket_source(surface, "ShaderNodeBackground") if surface else None
    if background is None:
        if w is not None:
            entry["color"] = list(w.color)[:3]
        entry_left = {"name": "world", "type": "WORLD", "reason": "not a Background"}
        not_exported["objects"].insert(0, entry_left)
        return entry
    entry["color"] = list(background.inputs["Color"].default_value)[:3]
    entry["strength"] = float(background.inputs["Strength"].default_value)
    texture = socket_source(background.inputs["Color"], "ShaderNodeTexEnvironment")
    if texture is None or texture.image is None:
        return entry
    image = texture.image
    extension = os.path.splitext(image.filepath)[1] or "." + image.file_format.lower()
    path = f"{stem}.world{extension.lower()}"
    if image.packed_file is not None:
        with open(path, "wb") as f:
            f.write(image.packed_file.data)
    else:
        shutil.copyfile(bpy.path.abspath(image.filepath, library=image.library), path)
    entry["environment"] = os.path.basename(path)
    mapping = socket_source(texture.inputs["Vector"], "ShaderNodeMapping")
    if mapping is not None:
        entry["rotation"] = list(mapping.inputs["Rotation"].default_value)
    return entry


def area_lights(depsgraph):
    """The sidecar's area lights."""
    return [
        {
            "name": name,
            "shape": data.shape,
            "size": [float(data.size), float(data.size_y)],
            "color": list(data.color),
            "power": float(data.energy),
            "matrix": [float(v) for v in common.to_gltf(matrix).ravel()],
        }
        for name, data, matrix in common.lights(depsgraph)
        if data.type == "AREA"
    ]


def listed(entries):
    """At most NAMES_LISTED entries, then one holding the count of the rest."""
    rest = len(entries) - NAMES_LISTED
    more = {"name": f"{rest} more", "type": "", "reason": ""}
    return entries[:NAMES_LISTED] + ([more] if rest > 0 else [])


def sidecar(source, depsgraph, stem, frame, left):
    """The sidecar's dictionary."""
    render, view = source.render, source.view_settings
    camera = source.camera or next(
        (o for o in source.objects if o.type == "CAMERA"), None
    )
    scale = render.resolution_percentage / 100
    not_exported = {
        "materials": [],
        "lights": [n for n, d, _ in common.lights(depsgraph) if d.type not in PUNCTUAL],
        "objects": listed(common.not_taken(depsgraph, left)),
    }
    lights = area_lights(depsgraph)
    not_exported["lights"] = [
        n for n in not_exported["lights"] if n not in {a["name"] for a in lights}
    ]
    return {
        "version": 1,
        "source": {
            "file": os.path.basename(bpy.data.filepath),
            "blender": bpy.app.version_string,
            "frame": frame,
        },
        "render": {
            "size": [
                int(render.resolution_x * scale),
                int(render.resolution_y * scale),
            ],
            "camera": camera.name if camera else None,
            "shift": [camera.data.shift_x, camera.data.shift_y] if camera else [0, 0],
            "sensor_fit": camera.data.sensor_fit if camera else None,
            "exposure": float(view.exposure),
            "view_transform": view.view_transform,
            "look": view.look,
            "gamma": float(view.gamma),
        },
        "world": world(source, stem, not_exported),
        "area_lights": lights,
        "instances": {"file": os.path.basename(stem) + ".instances.npz"},
        "not_exported": not_exported,
    }


def written(path):
    """{node name: triangles} of the meshes of a .glb's nodes, from its JSON chunk."""
    with open(path, "rb") as f:
        f.read(12)
        length, _ = struct.unpack("<II", f.read(8))
        document = json.loads(f.read(length))
    counts = {}
    for node in document.get("nodes", []):
        if "mesh" not in node:
            continue
        count = 0
        for primitive in document["meshes"][node["mesh"]]["primitives"]:
            if primitive.get("mode", TRIANGLES_MODE) == TRIANGLES_MODE:
                accessor = primitive.get("indices", primitive["attributes"]["POSITION"])
                count += document["accessors"][accessor]["count"] // 3
        counts[node.get("name")] = count
    return counts


def dropped(found, names, path):
    """The keys whose .glb mesh holds other than the triangles handed over."""
    counts = written(path)
    differences = []
    for key, name in zip(sorted(found), names, strict=True):
        expected, got = found[key]["triangles"], counts.get(name, 0)
        if got != expected:
            differences.append({"node": name, "expected": expected, "written": got})
    return differences


def lossy(rewritten):
    """The materials of class X or with a socket lost."""
    return [
        name
        for name, r in rewritten.items()
        if r["class"] == "X" or any(v["done"] == "lost" for v in r["sockets"].values())
    ]


def main():
    """Exports the open scene to the stem named on the command line."""
    parser = argparse.ArgumentParser()
    parser.add_argument("stem")
    parser.add_argument("--frame", type=int, default=None)
    args = parser.parse_args(common.arguments())
    started = time.perf_counter()
    source = bpy.context.scene
    if args.frame is not None:
        source.frame_set(args.frame)
    frame = source.frame_current
    common.render_visibility()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    found, bases, left = common.copies(depsgraph, keep=True)
    record = sidecar(source, depsgraph, args.stem, frame, left)
    scene, names = build_scene(found, depsgraph, source)
    rewritten, material_seconds, bakes = materials.Rewriter().run(materials.used(found))
    record["materials"] = rewritten
    record["not_exported"]["materials"] = lossy(rewritten)
    table(found, names, args.stem + ".instances.npz")
    bpy.context.window.scene = scene
    bpy.ops.export_scene.gltf(
        filepath=args.stem + ".glb",
        export_format="GLB",
        use_active_scene=True,
        export_apply=False,
        export_yup=True,
        export_cameras=True,
        export_lights=True,
        export_animations=False,
        export_skins=False,
        export_morph=False,
        export_tangents=True,
    )
    record["not_exported"]["triangles"] = dropped(found, names, args.stem + ".glb")
    with open(args.stem + ".prism.json", "w") as f:
        json.dump(record, f, indent=1)
    common.report(
        {
            "seconds": round(time.perf_counter() - started, 1),
            "glb_bytes": os.path.getsize(args.stem + ".glb"),
            "geometry_keys": len(found),
            "stored_triangles": sum(v["triangles"] for v in found.values()),
            "drawn_triangles": sum(
                v["triangles"] * len(v["matrices"]) for v in found.values()
            ),
            "copies": sum(len(v["matrices"]) for v in found.values()),
            "bases": len(bases),
            "bases_with_several_meshes": sum(n > 1 for n in bases.values()),
            "area_lights": len(record["area_lights"]),
            "materials": {
                c: sum(r["class"] == c for r in rewritten.values()) for c in "PSX"
            },
            "materials_with_losses": len(record["not_exported"]["materials"]),
            "material_seconds": material_seconds,
            "bakes": bakes,
            "nodes_with_dropped_triangles": len(record["not_exported"]["triangles"]),
            "triangles_not_exported": sum(
                d["expected"] - d["written"]
                for d in record["not_exported"]["triangles"]
            ),
        }
    )


main()
