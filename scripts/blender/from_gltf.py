"""Run inside Blender: an empty file, a .glb read by Blender's glTF importer, its instance
table (copies drawn by geometry nodes) and sidecar (render camera, world, area lights,
colour management) applied, saved as a .blend for `render.py` and `light_passes.py`.
`blender --background --factory-startup --python from_gltf.py -- <stem> <out.blend>`"""

import argparse
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import common
import mathutils
import numpy

MATRIX = "prism_matrix"
INVERSE = numpy.linalg.inv(common.AXES)


def to_blender(matrices):
    """glTF matrices (N, 4, 4), row-major, in Blender's axes."""
    return INVERSE @ matrices.astype(numpy.float64) @ common.AXES


def copies_group(obj):
    """Geometry nodes drawing `obj` at the points' `prism_matrix`."""
    group = bpy.data.node_groups.new(f"{obj.name}_copies", "GeometryNodeTree")
    group.interface.new_socket(
        "Geometry", in_out="INPUT", socket_type="NodeSocketGeometry"
    )
    group.interface.new_socket(
        "Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry"
    )
    nodes, links = group.nodes, group.links
    given = nodes.new("NodeGroupInput")
    info = nodes.new("GeometryNodeObjectInfo")
    info.transform_space = "ORIGINAL"
    info.inputs["Object"].default_value = obj
    place = nodes.new("GeometryNodeInstanceOnPoints")
    attribute = nodes.new("GeometryNodeInputNamedAttribute")
    attribute.data_type = "FLOAT4X4"
    attribute.inputs["Name"].default_value = MATRIX
    transform = nodes.new("GeometryNodeSetInstanceTransform")
    out = nodes.new("NodeGroupOutput")
    links.new(given.outputs["Geometry"], place.inputs["Points"])
    links.new(info.outputs["Geometry"], place.inputs["Instance"])
    links.new(place.outputs["Instances"], transform.inputs["Instances"])
    links.new(attribute.outputs["Attribute"], transform.inputs["Transform"])
    links.new(transform.outputs["Instances"], out.inputs["Geometry"])
    return group


def instances(scene, path):
    """Places each node of the table at its matrices: one copy by its own matrix, more
    by points carrying the matrices under `copies_group`; the number of copies."""
    table = numpy.load(path)
    names, starts, matrices = table["node_names"], table["starts"], table["matrices"]
    for i, name in enumerate(names):
        obj = bpy.data.objects[str(name)]
        block = to_blender(matrices[starts[i] : starts[i + 1]])
        if len(block) == 1:
            obj.matrix_world = mathutils.Matrix(block[0].tolist())
            continue
        mesh = bpy.data.meshes.new(f"{name}_copies")
        mesh.vertices.add(len(block))
        mesh.vertices.foreach_set("co", block[:, :3, 3].astype(numpy.float32).ravel())
        layer = mesh.attributes.new(MATRIX, "FLOAT4X4", "POINT")
        columns = block.transpose(0, 2, 1).astype(numpy.float32).ravel()
        layer.data.foreach_set("value", columns)
        holder = bpy.data.objects.new(f"{name}_copies", mesh)
        scene.collection.objects.link(holder)
        modifier = holder.modifiers.new("prism_copies", "NODES")
        modifier.node_group = copies_group(obj)
        obj.hide_render = True
    return int(starts[-1])


def camera(scene, render):
    """The render camera with the sidecar's fit, field of view and shift; its name."""
    obj = bpy.data.objects.get(render["camera"] or "")
    if obj is None or obj.type != "CAMERA":
        return None
    scene.camera = obj
    data = obj.data
    width, height = render["size"]
    aspect = width / height
    yfov = data.angle_y
    xfov = 2 * math.atan(aspect * math.tan(yfov / 2))
    fit = render.get("sensor_fit") or "AUTO"
    data.sensor_fit = fit
    if fit == "VERTICAL":
        data.angle_y = yfov
    elif fit == "HORIZONTAL":
        data.angle_x = xfov
    else:
        data.angle_x = max(xfov, yfov)
    data.shift_x, data.shift_y = render.get("shift", (0.0, 0.0))
    return obj.name


def world(scene, entry, folder):
    """A world of a Background node: the sidecar's colour, strength and map."""
    scene.world = bpy.data.worlds.new("prism_world")
    scene.world.use_nodes = True
    nodes, links = scene.world.node_tree.nodes, scene.world.node_tree.links
    background = next(n for n in nodes if n.bl_idname == "ShaderNodeBackground")
    background.inputs["Color"].default_value = (*entry["color"], 1.0)
    background.inputs["Strength"].default_value = entry["strength"]
    if not entry.get("environment"):
        return
    texture = nodes.new("ShaderNodeTexEnvironment")
    texture.image = bpy.data.images.load(os.path.join(folder, entry["environment"]))
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Rotation"].default_value = entry.get("rotation", (0, 0, 0))
    coordinates = nodes.new("ShaderNodeTexCoord")
    links.new(coordinates.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], texture.inputs["Vector"])
    links.new(texture.outputs["Color"], background.inputs["Color"])


def area_lights(scene, entries):
    """The sidecar's area lights as Blender area lights."""
    for entry in entries:
        data = bpy.data.lights.new(entry["name"], "AREA")
        data.shape = entry["shape"]
        data.size, data.size_y = entry["size"]
        data.color = entry["color"]
        data.energy = entry["power"]
        obj = bpy.data.objects.new(entry["name"], data)
        matrix = numpy.array(entry["matrix"], dtype=numpy.float64).reshape(1, 4, 4)
        obj.matrix_world = mathutils.Matrix(to_blender(matrix)[0].tolist())
        scene.collection.objects.link(obj)
    return len(entries)


def colour(scene, render):
    """The sidecar's render size and colour management; EXR passes in one part."""
    scene.render.resolution_x, scene.render.resolution_y = render["size"]
    scene.render.resolution_percentage = 100
    scene.render.image_settings.use_exr_interleave = True
    view = scene.view_settings
    view.view_transform = render["view_transform"]
    view.look = render["look"]
    view.exposure = render["exposure"]
    view.gamma = render["gamma"]


def main():
    """Builds the scene of the stem named on the command line and saves it."""
    parser = argparse.ArgumentParser()
    parser.add_argument("stem")
    parser.add_argument("out")
    args = parser.parse_args(common.arguments())
    started = time.perf_counter()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    bpy.ops.import_scene.gltf(filepath=args.stem + ".glb")
    imported = time.perf_counter() - started
    with open(args.stem + ".prism.json") as f:
        sidecar = json.load(f)
    folder = os.path.dirname(os.path.abspath(args.stem))
    count = instances(scene, os.path.join(folder, sidecar["instances"]["file"]))
    colour(scene, sidecar["render"])
    name = camera(scene, sidecar["render"])
    world(scene, sidecar["world"], folder)
    areas = area_lights(scene, sidecar["area_lights"])
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.out))
    common.report(
        {
            "seconds": round(time.perf_counter() - started, 1),
            "import_seconds": round(imported, 1),
            "copies": count,
            "camera": name,
            "area_lights": areas,
            "lights": sum(o.type == "LIGHT" for o in scene.objects) - areas,
        }
    )


main()
