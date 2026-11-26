"""Helpers the scripts run inside Blender share: the copies of each geometry, triangle
counts, Blender's axes to glTF's, material and world graph walks."""

import json
import sys

import bpy
import numpy

GEOMETRY = {"MESH", "CURVE", "SURFACE", "FONT", "META"}
NOT_TAKEN = {"CURVES", "POINTCLOUD", "VOLUME", "GPENCIL", "GREASEPENCIL"}
AXES = numpy.array(
    [[1, 0, 0, 0], [0, 0, 1, 0], [0, -1, 0, 0], [0, 0, 0, 1]], dtype=numpy.float64
)


def arguments():
    """The arguments after `--` on Blender's command line."""
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def report(record):
    """Prints the one JSON line of a script."""
    print(json.dumps(record), flush=True)


def triangles(evaluated_object):
    """The triangle count of an evaluated object's mesh."""
    mesh = evaluated_object.to_mesh()
    mesh.calc_loop_triangles()
    count = len(mesh.loop_triangles)
    evaluated_object.to_mesh_clear()
    return count


def base_of(original):
    """The base of the geometry key of a copy of `original`."""
    data = original.data
    if original.type != "MESH" or original.modifiers or data.shape_keys:
        return ("object", original.name_full)
    return ("data", data.name_full)


def copies(depsgraph, keep=False):
    """{key: {"source", "triangles", "matrices"}} over the depsgraph's instances of
    geometry with triangles, a key being base + (k,), k numbering a base's evaluated
    data; `source` is a mesh made at the key's first copy when `keep`. Also {base: k's}.
    """
    found = {}
    keys = {}
    bases = {}
    for instance in depsgraph.object_instances:
        evaluated = instance.object
        if evaluated.type not in GEOMETRY:
            continue
        base = base_of(evaluated.original)
        pointer = (base, evaluated.data.as_pointer() if evaluated.data else 0)
        if pointer not in keys:
            count = triangles(evaluated)
            keys[pointer] = (None, 0)
            if count:
                bases[base] = bases.get(base, 0) + 1
                keys[pointer] = ((*base, bases[base] - 1), count)
        key, count = keys[pointer]
        if key is None:
            continue
        if key not in found:
            source = None
            if keep and instance.is_instance:
                source = bpy.data.meshes.new_from_object(evaluated)
            elif keep:
                source = bpy.data.meshes.new_from_object(
                    evaluated, preserve_all_data_layers=True, depsgraph=depsgraph
                )
            found[key] = {"source": source, "triangles": count, "matrices": []}
        found[key]["matrices"].append(instance.matrix_world.copy())
    return found, bases


def to_gltf(matrix):
    """A world matrix in Blender's axes as glTF's, row-major (4, 4) float32."""
    m = numpy.array(matrix, dtype=numpy.float64)
    return (AXES @ m @ numpy.linalg.inv(AXES)).astype(numpy.float32)


def lights(depsgraph):
    """[(name, light data, world matrix copy)] of every light the depsgraph draws."""
    return [
        (i.object.original.name, i.object.original.data, i.matrix_world.copy())
        for i in depsgraph.object_instances
        if i.object.type == "LIGHT"
    ]


def not_taken(depsgraph):
    """Names of render-visible objects of a type `copies` does not take."""
    names = []
    for instance in depsgraph.object_instances:
        original = instance.object.original
        visible = instance.object.type in NOT_TAKEN and not original.hide_render
        if visible and original.name_full not in names:
            names.append(original.name_full)
    return names


def upstream(socket, kinds):
    """Nodes of a type in `kinds` linked upstream of `socket`, also inside groups."""
    seen, found, stack = set(), [], [socket]
    while stack:
        current = stack.pop()
        for link in current.links if current.is_linked else ():
            node = link.from_node
            if node.as_pointer() in seen:
                continue
            seen.add(node.as_pointer())
            if node.bl_idname in kinds:
                found.append(node)
            if node.bl_idname == "ShaderNodeGroup" and node.node_tree:
                for inner in node.node_tree.nodes:
                    if inner.bl_idname == "NodeGroupOutput":
                        stack.extend(inner.inputs)
            stack.extend(node.inputs)
    return found


def output_node(tree):
    """The active output node of a node tree, or None."""
    if tree is None:
        return None
    for target in ("ALL", "CYCLES", "EEVEE"):
        node = tree.get_output_node(target)
        if node is not None:
            return node
    return None


def principled(material):
    """The Principled BSDF nodes reaching a material's active output."""
    output = output_node(material.node_tree)
    if output is None or "Surface" not in output.inputs:
        return []
    return upstream(output.inputs["Surface"], {"ShaderNodeBsdfPrincipled"})
