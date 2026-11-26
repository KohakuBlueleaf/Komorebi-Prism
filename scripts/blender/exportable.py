"""Run inside Blender: what Blender's glTF exporter can carry of the open scene, per
material, weighted by the drawn triangles, world area and picture share of its users.
`blender --background <file.blend> --python exportable.py -- <out.json> [--rays W H]`
"""

import argparse
import json
import os
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import common
import graph
from mathutils import Vector

SHADER_MIX = {"ShaderNodeMixShader", "ShaderNodeAddShader"}
PRINCIPLED = "ShaderNodeBsdfPrincipled"
IMAGE = "ShaderNodeTexImage"
ATTRIBUTE = {"ShaderNodeVertexColor", "ShaderNodeAttribute"}
MULTIPLY_OK = {"ShaderNodeMix", "ShaderNodeMixRGB", "ShaderNodeMath"}
VECTOR_SIDE = {"ShaderNodeTexCoord", "ShaderNodeUVMap", "ShaderNodeMapping"}
STAND_IN_NODES = {"GeometryNodeIsViewport"}
COLOUR_INPUTS = {
    "ShaderNodeMix": ("A", "B"),
    "ShaderNodeMixRGB": ("Color1", "Color2"),
    "ShaderNodeHueSaturation": ("Color",),
    "ShaderNodeGamma": ("Color",),
    "ShaderNodeBrightContrast": ("Color",),
    "ShaderNodeRGBCurve": ("Color",),
    "ShaderNodeInvert": ("Color",),
    "ShaderNodeCombineColor": ("Red", "Green", "Blue"),
    "ShaderNodeSeparateColor": ("Color",),
}
NO_MATERIAL = "<none>"
WORLD = "<world>"
HIDDEN = "<camera rays off>"
PASSES = 16
CLEAR = {}  # material name: why camera rays pass it, filled at the first ray
STEP = 1e-4


def leaves(path, socket, out):
    """The shader nodes feeding `socket` through mix and add shaders: appends
    (path, node) to `out`; returns True when a mix or add was passed."""
    found = graph.resolve(path, socket)
    if found[0] == "const":
        return False
    _, at, src = found
    node = src.node
    if node.bl_idname not in SHADER_MIX:
        out.append((at, node))
        return False
    for entry in node.inputs:
        if entry.type == "SHADER":
            leaves(at, entry, out)
    return True


def upstream_kinds(path, socket):
    """{node type: count} of every node upstream of an input, groups walked through."""
    found = graph.resolve(path, socket)
    if found[0] == "const":
        return {}
    kinds, seen, stack = Counter(), set(), [(found[1], found[2])]
    while stack:
        at, out = stack.pop()
        node = out.node
        key = (graph.names(at), node.name)
        if key in seen:
            continue
        seen.add(key)
        kinds[node.bl_idname] += 1
        for entry in node.inputs:
            inner = graph.resolve(at, entry)
            if inner[0] == "out":
                stack.append((inner[1], inner[2]))
    return dict(kinds)


def image_present(image):
    """True when an image has pixels Blender can read (packed, generated or on disk)."""
    if image is None:
        return False
    if image.packed_file is not None or image.source == "GENERATED":
        return True
    if image.source == "TILED":
        return True
    path = bpy.path.abspath(image.filepath, library=image.library)
    return os.path.exists(path)


def image_nodes(path, socket):
    """The image texture nodes upstream of an input, groups walked through."""
    found, seen, stack = [], set(), [(tuple(path), socket)]
    while stack:
        at, entry = stack.pop()
        resolved = graph.resolve(at, entry)
        if resolved[0] == "const":
            continue
        _, inner, out = resolved
        key = (graph.names(inner), out.node.name)
        if key in seen:
            continue
        seen.add(key)
        if out.node.bl_idname == IMAGE:
            found.append(out.node)
        stack.extend((inner, i) for i in out.node.inputs)
    return found


def written_image(path, socket, seen=None):
    """The image node the exporter writes for an input: the first one of a depth-first
    search that takes each node before its inputs, inputs in order (its NodeTreeSearcher).
    """
    seen = set() if seen is None else seen
    resolved = graph.resolve(path, socket)
    if resolved[0] == "const":
        return None
    _, inner, out = resolved
    key = (graph.names(inner), out.node.name)
    if key in seen:
        return None
    seen.add(key)
    if out.node.bl_idname == IMAGE:
        return out.node
    for entry in out.node.inputs:
        found = written_image(inner, entry, seen)
        if found is not None:
            return found
    return None


def colour_images(path, socket):
    """The names of the image nodes whose Color output reaches an input through colour
    inputs only."""
    found, seen, stack = set(), set(), [(tuple(path), socket)]
    while stack:
        at, entry = stack.pop()
        resolved = graph.resolve(at, entry)
        if resolved[0] == "const":
            continue
        _, inner, out = resolved
        node = out.node
        key = (graph.names(inner), node.name)
        if key in seen:
            continue
        seen.add(key)
        if node.bl_idname == IMAGE and out.name == "Color":
            found.add(key)
            continue
        names = COLOUR_INPUTS.get(node.bl_idname, ())
        stack.extend((inner, i) for i in node.inputs if i.name in names and i.enabled)
    return found


def colour_path(path, socket):
    """True when an image reaches a colour input through colour inputs only (a tint),
    False when every image reaches it through a factor, ramp or math (a mask)."""
    seen, stack = set(), [(tuple(path), socket)]
    while stack:
        at, entry = stack.pop()
        found = graph.resolve(at, entry)
        if found[0] == "const":
            continue
        _, inner, out = found
        node = out.node
        key = (graph.names(inner), node.name)
        if key in seen:
            continue
        seen.add(key)
        if node.bl_idname == IMAGE and out.name == "Color":
            return True
        names = COLOUR_INPUTS.get(node.bl_idname, ())
        stack.extend((inner, i) for i in node.inputs if i.name in names and i.enabled)
    return False


def colour_input(path, socket):
    """How the exporter writes a colour input of the Principled BSDF: "constant",
    "image", "image_altered" (other nodes between it and the image, dropped), "attribute",
    "lost" (written as white); with the node types upstream and missing images."""
    found = graph.resolve(path, socket)
    if found[0] == "const":
        return {"kind": "constant"}
    _, at, src = found
    if src.node.bl_idname in graph.CONSTANT:
        return {"kind": "constant"}
    kinds = upstream_kinds(path, socket)
    try:
        info = graph.chain(at, src)
    except KeyError:
        info = {"images": [], "geometry": "unreadable", "undefined": None}
        info["images"] = image_nodes(path, socket)
    images = info["images"]
    entry = {"nodes": kinds}
    if images:
        missing = [i.image.name if i.image else None for i in images]
        missing = [n for n, i in zip(missing, images) if not image_present(i.image)]
        between = {
            k: v
            for k, v in kinds.items()
            if k not in VECTOR_SIDE and k != IMAGE and k not in graph.CONSTANT
        }
        altered = len(images) > 1 or any(k not in MULTIPLY_OK for k in between)
        altered = altered or sum(between.values()) > 1
        entry["kind"] = "image_altered" if altered else "image"
        entry["colour_path"] = colour_path(path, socket)
        written = written_image(path, socket)
        if written is not None and written.image is not None:
            image = written.image
            entry["written"] = {
                "image": image.name,
                "colour_space": image.colorspace_settings.name,
                "on_colour_path": any(
                    k[1] == written.name for k in colour_images(path, socket)
                ),
            }
        entry["missing"] = missing
        entry["geometry"] = info["geometry"]
        return entry
    if src.node.bl_idname in ATTRIBUTE:
        entry["kind"] = "attribute"
        return entry
    entry["kind"] = "lost"
    entry["geometry"] = info["geometry"]
    entry["undefined"] = info["undefined"]
    entry["procedural"] = sorted(k for k in kinds if k in graph.PROCEDURAL)
    return entry


def normal_input(path, node):
    """How the Normal input is written: "none", "normal_map" (an image through a Normal
    Map), "bump_as_normal" (an image through a Bump, written as a normal map), "lost".
    """
    socket = node.inputs.get("Normal")
    if socket is None:
        return "none"
    found = graph.resolve(path, socket)
    if found[0] == "const":
        return "none"
    kinds = upstream_kinds(path, socket)
    if IMAGE not in kinds:
        return "lost"
    if "ShaderNodeBump" in kinds:
        return "bump_as_normal"
    return "normal_map" if "ShaderNodeNormalMap" in kinds else "image_other"


def value_of(node, name):
    """A float input's value, or -1 when it is linked, or None when it is absent."""
    socket = node.inputs.get(name)
    if socket is None:
        return None
    return -1.0 if socket.is_linked else float(socket.default_value)


def material_entry(material):
    """What the exporter can carry of one material."""
    entry = {"surface": "none", "leaves": [], "base": None, "normal": None}
    output = common.output_node(material.node_tree) if material.use_nodes else None
    if output is None:
        entry["surface"] = "no nodes"
        return entry
    for name in ("Displacement", "Volume"):
        socket = output.inputs.get(name)
        entry[name.lower()] = bool(socket is not None and socket.is_linked)
    found = []
    mixed = (
        leaves((), output.inputs["Surface"], found)
        if "Surface" in output.inputs
        else False
    )
    entry["leaves"] = sorted(Counter(n.bl_idname for _, n in found).items())
    entry["mixed"] = mixed
    principled = [(at, n) for at, n in found if n.bl_idname == PRINCIPLED]
    if not found:
        entry["surface"] = "volume only" if entry.get("volume") else "none"
        return entry
    if not principled:
        kinds = {n.bl_idname for _, n in found}
        only_emit = kinds <= {"ShaderNodeEmission", "ShaderNodeBsdfTransparent"}
        entry["surface"] = "emission" if only_emit else "other_bsdf"
        return entry
    entry["surface"] = "principled" if not mixed else "mix_principled"
    at, node = principled[0]
    entry["base"] = colour_input(at, node.inputs["Base Color"])
    entry["normal"] = normal_input(at, node)
    for name in ("Roughness", "Metallic"):
        socket = node.inputs.get(name)
        if socket is not None:
            entry[name.lower()] = colour_input(at, socket)["kind"]
    entry["alpha"] = value_of(node, "Alpha")
    entry["transmission"] = value_of(node, "Transmission Weight")
    entry["emission_strength"] = value_of(node, "Emission Strength")
    return entry


def scale_of(matrix):
    """The area factor of a world matrix (exact for a uniform scale)."""
    return abs(matrix.to_3x3().determinant()) ** (2.0 / 3.0)


def drawn(depsgraph):
    """{material: [triangles, area]} over the instances camera rays see, and the
    triangles of objects whose geometry nodes test for the viewport (stand-ins)."""
    transparent = {m.name_full: common.see_through(m) for m in bpy.data.materials}
    per_data, totals, stand_in = {}, Counter(), Counter()
    flagged = stand_in_objects()
    for instance in depsgraph.object_instances:
        evaluated = instance.object
        if evaluated.type not in common.GEOMETRY:
            continue
        if common.camera_rule(instance, transparent) is not None:
            continue
        slots = tuple(
            s.material.name_full if s.material else NO_MATERIAL
            for s in evaluated.material_slots
        )
        key = (evaluated.data.as_pointer() if evaluated.data else 0, slots)
        if key not in per_data:
            per_data[key] = mesh_counts(evaluated, slots)
        factor = scale_of(instance.matrix_world)
        owner = (
            instance.parent.original
            if instance.is_instance and instance.parent
            else evaluated.original
        )
        for name, (count, area) in per_data[key].items():
            totals[(name, "triangles")] += count
            totals[(name, "area")] += area * factor
            if owner.name_full in flagged or evaluated.original.name_full in flagged:
                stand_in[owner.name_full] += count
    out = {}
    for (name, what), value in totals.items():
        out.setdefault(name, {"triangles": 0, "area": 0.0})[what] = value
    return out, dict(stand_in)


def mesh_counts(evaluated, slots):
    """{material: (triangles, local area)} of an evaluated object's mesh."""
    mesh = evaluated.to_mesh()
    if mesh is None:
        return {}
    mesh.calc_loop_triangles()
    counts, areas = Counter(), Counter()
    for triangle in mesh.loop_triangles:
        index = triangle.material_index
        name = slots[index] if 0 <= index < len(slots) else NO_MATERIAL
        counts[name] += 1
        areas[name] += triangle.area
    evaluated.to_mesh_clear()
    return {name: (counts[name], areas[name]) for name in counts}


def tree_has(tree, kinds, seen):
    """True when a node tree (or a group inside it) holds a node of `kinds`."""
    if tree is None or tree.name_full in seen:
        return False
    seen.add(tree.name_full)
    for node in tree.nodes:
        if node.bl_idname in kinds:
            return True
        if getattr(node, "node_tree", None) is not None and tree_has(
            node.node_tree, kinds, seen
        ):
            return True
    return False


def stand_in_objects():
    """Names of objects whose geometry-node modifiers read whether this is the viewport."""
    names = set()
    for obj in bpy.data.objects:
        for modifier in obj.modifiers:
            if modifier.type == "NODES" and tree_has(
                modifier.node_group, STAND_IN_NODES, set()
            ):
                names.add(obj.name_full)
    return names


def picture(scene, depsgraph, width, height):
    """{material: share of the camera's picture} by one ray a cell of a width x height
    grid; WORLD for rays that hit nothing."""
    camera = scene.camera
    if camera is None:
        return {}, {}
    evaluated = camera.evaluated_get(depsgraph)
    matrix = evaluated.matrix_world
    frame = [matrix @ v for v in evaluated.data.view_frame(scene=scene)]
    origin = matrix.translation
    top_right, bottom_right, bottom_left, top_left = frame
    hits, faces, passed = Counter(), {}, Counter()
    for j in range(height):
        v = (j + 0.5) / height
        left = top_left.lerp(bottom_left, v)
        right = top_right.lerp(bottom_right, v)
        for i in range(width):
            target = left.lerp(right, (i + 0.5) / width)
            if evaluated.data.type == "ORTHO":
                start, direction = target, (matrix.to_3x3() @ Vector((0, 0, -1)))
            else:
                ray = (target - origin).normalized()
                start, direction = origin + ray * evaluated.data.clip_start, ray
            name = first_seen(
                scene, depsgraph, start, direction.normalized(), faces, passed
            )
            hits[name] += 1
    total = width * height
    return {k: v / total for k, v in hits.items()}, {
        k: v / total for k, v in passed.items()
    }


def passes(material):
    """Why camera rays pass a material: `common.see_through`, or "mostly transparent" when
    its surface is a Principled BSDF with a constant alpha under 0.5; None otherwise."""
    why = common.see_through(material)
    if why is not None:
        return why
    output = common.output_node(material.node_tree) if material.use_nodes else None
    if output is None or "Surface" not in output.inputs:
        return None
    found = graph.resolve((), output.inputs["Surface"])
    if found[0] == "const" or found[2].node.bl_idname != PRINCIPLED:
        return None
    alpha = graph.resolve(found[1], found[2].node.inputs["Alpha"])
    if alpha[0] == "const" and isinstance(alpha[1], float) and alpha[1] < 0.5:
        return "mostly transparent"
    return None


def first_seen(scene, depsgraph, start, direction, faces, passed):
    """The material a camera ray sees first, passing materials camera rays pass
    (`passes`), each pass counted in `passed`."""
    name = NO_MATERIAL
    for _ in range(PASSES):
        hit, location, _, index, obj, _ = scene.ray_cast(depsgraph, start, direction)
        if not hit:
            return WORLD
        original = obj.original
        if not original.visible_camera or original.is_holdout:
            passed[HIDDEN] += 1
            start = location + direction * STEP
            continue
        name = hit_material(obj, index, depsgraph, faces)
        if not CLEAR:
            CLEAR.update((m.name_full, passes(m)) for m in bpy.data.materials)
        if CLEAR.get(name) is None:
            return name
        passed[name] += 1
        start = location + direction * STEP
    return name


def face_slots(obj, depsgraph):
    """The material slot of each polygon of an object's evaluated mesh, and its slots."""
    evaluated = obj.evaluated_get(depsgraph)
    try:
        mesh = evaluated.to_mesh()
    except RuntimeError:
        mesh = None
    if mesh is None:
        return [], []
    found = [p.material_index for p in mesh.polygons]
    evaluated.to_mesh_clear()
    return found, [s.material for s in evaluated.material_slots]


def hit_material(obj, index, depsgraph, faces):
    """The material of polygon `index` of a ray's object (`faces` caches its mesh)."""
    key = obj.name_full
    if key not in faces:
        faces[key] = face_slots(obj, depsgraph)
    polygons, slots = faces[key]
    if index < 0 or index >= len(polygons):
        return NO_MATERIAL
    slot = polygons[index]
    if slot >= len(slots) or slots[slot] is None:
        return NO_MATERIAL
    return slots[slot].name_full


def not_taken(depsgraph):
    """{"type: reason": objects} of what Cycles draws and the export does not carry (hair
    strands, curves, a world volume), the objects hidden in the render left out."""
    found = Counter()
    for entry in common.not_taken(depsgraph, {}):
        if entry["reason"] != "hidden in the render":
            found[f"{entry['type']}: {entry['reason']}"] += 1
    return dict(found)


def world_kind(scene):
    """The world as the exporter's sidecar sees it."""
    w = scene.world
    output = common.output_node(w.node_tree) if w and w.use_nodes else None
    if output is None:
        return {"kind": "colour" if w else "none"}
    surface = output.inputs.get("Surface")
    volume = output.inputs.get("Volume")
    entry = {"volume": bool(volume is not None and volume.is_linked)}
    found = graph.resolve((), surface) if surface is not None else ("const", None)
    if found[0] == "const":
        entry["kind"] = "none"
        return entry
    node = found[2].node
    if node.bl_idname != "ShaderNodeBackground":
        entry["kind"] = f"not a Background ({node.bl_idname})"
        entry["nodes"] = upstream_kinds((), surface)
        return entry
    colour = node.inputs["Color"]
    source = graph.resolve(found[1], colour)
    if source[0] == "const":
        entry["kind"] = "constant"
    elif source[2].node.bl_idname == "ShaderNodeTexEnvironment":
        image = source[2].node.image
        entry["kind"] = "environment map"
        entry["present"] = image_present(image)
        entry["file"] = os.path.splitext(image.filepath)[1].lower() if image else None
    else:
        entry["kind"] = f"Background fed by {source[2].node.bl_idname}"
        entry["nodes"] = upstream_kinds(found[1], colour)
    return entry


def missing_libraries():
    """Linked libraries whose file is not on disk."""
    return [
        lib.filepath
        for lib in bpy.data.libraries
        if not os.path.exists(bpy.path.abspath(lib.filepath))
    ]


def camera_animated(scene):
    """True when the camera's object or data carries an action."""
    camera = scene.camera
    if camera is None:
        return False
    return any(
        getattr(owner, "animation_data", None) is not None
        and owner.animation_data.action is not None
        for owner in (camera, camera.data)
    )


def main():
    """Measures the open scene into the JSON file named on the command line."""
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--rays", type=int, nargs=2, default=(160, 90))
    args = parser.parse_args(common.arguments())
    started = time.perf_counter()
    scene = bpy.context.scene
    common.render_visibility()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    weights, stand_in = drawn(depsgraph)
    measured = time.perf_counter()
    shares, passed = picture(scene, depsgraph, *args.rays)
    used = set(weights) | set(shares) | set(passed)
    materials = {}
    for name in sorted(used - {NO_MATERIAL, WORLD, HIDDEN}):
        material = bpy.data.materials.get(name) or next(
            (m for m in bpy.data.materials if m.name_full == name), None
        )
        materials[name] = (
            material_entry(material) if material else {"surface": "absent"}
        )
    for name, entry in materials.items():
        entry |= weights.get(name, {"triangles": 0, "area": 0.0})
        entry["picture"] = shares.get(name, 0.0)
        entry["picture_passed"] = passed.get(name, 0.0)
    missing_images = sorted(
        i.name_full
        for i in bpy.data.images
        if i.source in {"FILE", "SEQUENCE", "MOVIE"} and not image_present(i)
    )
    record = {
        "file": bpy.data.filepath,
        "materials": materials,
        "no_material": weights.get(NO_MATERIAL, {})
        | {"picture": shares.get(NO_MATERIAL, 0.0)},
        "world_picture": shares.get(WORLD, 0.0),
        "hidden_passed": passed.get(HIDDEN, 0.0),
        "lights": dict(Counter(d.type for _, d, _ in common.lights(depsgraph))),
        "portals": sum(
            1
            for _, d, _ in common.lights(depsgraph)
            if d.type == "AREA" and getattr(d.cycles, "is_portal", False)
        ),
        "world": world_kind(scene),
        "not_taken": not_taken(depsgraph),
        "stand_in_triangles": stand_in,
        "missing_libraries": missing_libraries(),
        "missing_images": missing_images,
        "camera_animated": camera_animated(scene),
        "camera": scene.camera.name if scene.camera else None,
        "engine": scene.render.engine,
        "seconds_weights": round(measured - started, 1),
        "seconds_picture": round(time.perf_counter() - measured, 1),
    }
    with open(args.out, "w") as f:
        json.dump(record, f, indent=1)
    common.report(
        {
            "out": args.out,
            "materials": len(materials),
            "triangles": sum(e.get("triangles", 0) for e in materials.values()),
            "seconds": round(time.perf_counter() - started, 1),
        }
    )


main()
