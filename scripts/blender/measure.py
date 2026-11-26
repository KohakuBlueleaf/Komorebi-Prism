"""Run inside Blender: what an open scene holds, as one JSON file; no rendering.
`blender --background <file.blend> --python measure.py -- <out.json>`"""

import json
import os
import re
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import common

TEXTURE = {"ShaderNodeTexImage"}
VOLUME_OUTPUT = "Volume"
README_CHARACTERS = 2000
LARGE_SIDE = 4096


def linked_or_above(node, name, floor=0.0):
    """True when an input is linked or its value is above `floor`."""
    socket = node.inputs.get(name)
    if socket is None:
        return False
    return socket.is_linked or float(socket.default_value) > floor


def coloured(node, name):
    """True when a colour input is linked or not black."""
    socket = node.inputs.get(name)
    if socket is None:
        return False
    return socket.is_linked or any(c > 0 for c in list(socket.default_value)[:3])


def textured(nodes, names):
    """True when an image texture feeds one of the inputs `names` of any node."""
    return any(
        common.upstream(node.inputs[name], TEXTURE)
        for node in nodes
        for name in names
        if name in node.inputs
    )


def materials():
    """Material counts by what their node trees hold."""
    counts = Counter()
    for material in bpy.data.materials:
        counts["all"] += 1
        output = common.output_node(material.node_tree)
        if output is None:
            continue
        found = common.principled(material)
        if found:
            counts["principled"] += 1
        if textured(found, ("Base Color",)):
            counts["base_colour_texture"] += 1
        if textured(found, ("Normal",)):
            counts["normal_texture"] += 1
        if textured(found, ("Roughness", "Metallic")):
            counts["roughness_or_metallic_texture"] += 1
        if any(linked_or_above(n, "Transmission Weight") for n in found):
            counts["transmissive"] += 1
        emission = "Surface" in output.inputs and common.upstream(
            output.inputs["Surface"], {"ShaderNodeEmission"}
        )
        if emission or any(
            linked_or_above(n, "Emission Strength") and coloured(n, "Emission Color")
            for n in found
        ):
            counts["emissive"] += 1
        if VOLUME_OUTPUT in output.inputs and output.inputs[VOLUME_OUTPUT].is_linked:
            counts["volume"] += 1
        if "Displacement" in output.inputs and output.inputs["Displacement"].is_linked:
            counts["displacement"] += 1
    return dict(counts)


def blender_triangles(statistics):
    """The triangle number of Blender's scene statistics text, or None."""
    found = re.search(r"Tri(?:angle)?s:? ?([0-9,]+)", statistics)
    return int(found.group(1).replace(",", "")) if found else None


def readme():
    """The first characters of a text datablock named README, or ""."""
    text = bpy.data.texts.get("README")
    return text.as_string()[:README_CHARACTERS] if text else ""


def main():
    """Measures the open scene into the JSON file named on the command line."""
    started = time.perf_counter()
    out = common.arguments()[0]
    scene = bpy.context.scene
    depsgraph = bpy.context.evaluated_depsgraph_get()
    found, bases = common.copies(depsgraph)
    statistics = bpy.context.scene.statistics(bpy.context.view_layer)
    real = Counter(
        i.object.type for i in depsgraph.object_instances if not i.is_instance
    )
    images = {i.name: list(i.size) for i in bpy.data.images if i.size[0] and i.size[1]}
    view = scene.view_settings
    record = {
        "file": os.path.basename(bpy.data.filepath),
        "blender": bpy.app.version_string,
        "geometry_keys": len(found),
        "stored_triangles": sum(v["triangles"] for v in found.values()),
        "drawn_triangles": sum(
            v["triangles"] * len(v["matrices"]) for v in found.values()
        ),
        "copies": sum(len(v["matrices"]) for v in found.values()),
        "bases": len(bases),
        "bases_with_several_meshes": sum(n > 1 for n in bases.values()),
        "blender_triangles": blender_triangles(statistics),
        "blender_statistics": statistics,
        "objects": dict(real),
        "materials": materials(),
        "images": images,
        "images_4k_or_more": sum(max(s) >= LARGE_SIDE for s in images.values()),
        "lights": dict(Counter(d.type for _, d, _ in common.lights(depsgraph))),
        "cameras": sum(1 for o in scene.objects if o.type == "CAMERA"),
        "armatures": len(bpy.data.armatures),
        "actions": len(bpy.data.actions),
        "shape_key_sets": len(bpy.data.shape_keys),
        "modifiers": dict(Counter(m.type for o in scene.objects for m in o.modifiers)),
        "engine": scene.render.engine,
        "resolution": [scene.render.resolution_x, scene.render.resolution_y],
        "resolution_percentage": scene.render.resolution_percentage,
        "frames": [scene.frame_start, scene.frame_end, scene.frame_current],
        "view_transform": view.view_transform,
        "readme": readme(),
    }
    with open(out, "w") as f:
        json.dump(record, f, indent=1)
    common.report(
        {
            k: record[k]
            for k in (
                "file",
                "geometry_keys",
                "stored_triangles",
                "drawn_triangles",
                "copies",
                "bases",
                "bases_with_several_meshes",
                "blender_triangles",
                "lights",
            )
        }
        | {"seconds": round(time.perf_counter() - started, 1)}
    )


main()
