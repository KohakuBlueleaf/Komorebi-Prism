"""Helpers the scripts run inside Blender share: the copies of each geometry, triangle
counts, Blender's axes to glTF's, material and world graph walks."""

import json
import sys

import bpy
import numpy

GEOMETRY = {"MESH", "CURVE", "SURFACE", "FONT", "META"}
NOT_TAKEN = {"CURVES", "POINTCLOUD", "VOLUME", "GPENCIL", "GREASEPENCIL"}
LEVELS = {"SUBSURF", "MULTIRES"}
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
    """The triangle count of an evaluated object's mesh; None when it gives no mesh."""
    mesh = evaluated_object.to_mesh()
    if mesh is None:
        return None
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


def render_visibility():
    """Sets, in this session only, what the viewport evaluates to what the render
    evaluates: visibility, modifiers, subdivision levels, instancers and particles.
    Returns the names of the objects and collections it could not change."""
    fixed = []
    stack = [bpy.context.view_layer.layer_collection]
    while stack:
        layer_collection = stack.pop()
        layer_collection.hide_viewport = False
        stack.extend(layer_collection.children)
    for collection in bpy.data.collections:
        try:
            collection.hide_viewport = collection.hide_render
        except (AttributeError, RuntimeError):
            fixed.append(collection.name_full)
    view_layer = bpy.context.view_layer
    for obj in bpy.data.objects:
        try:
            obj.hide_viewport = obj.hide_render
            obj.show_instancer_for_viewport = obj.show_instancer_for_render
            for modifier in obj.modifiers:
                modifier.show_viewport = modifier.show_render
                if modifier.type in LEVELS:
                    modifier.levels = modifier.render_levels
        except (AttributeError, RuntimeError):
            fixed.append(obj.name_full)
        if view_layer.objects.get(obj.name_full) is not None:
            obj.hide_set(False)
    for settings in bpy.data.particles:
        try:
            settings.display_percentage = 100
            settings.child_percent = settings.rendered_child_count
            settings.display_method = "RENDER"
        except (AttributeError, RuntimeError):
            fixed.append(settings.name_full)
    return fixed


def clear(socket):
    """True when the shader feeding `socket` lets a camera ray through untouched but for
    light it adds: a Transparent BSDF, a Principled BSDF of unlinked alpha 0, an Add
    Shader of such a shader and an emission (or of two such shaders)."""
    if not socket.is_linked:
        return False
    node = socket.links[0].from_node
    while node.bl_idname == "NodeReroute" and node.inputs[0].is_linked:
        node = node.inputs[0].links[0].from_node
    if node.bl_idname == "ShaderNodeBsdfTransparent":
        return True
    if node.bl_idname == "ShaderNodeBsdfPrincipled":
        alpha = node.inputs["Alpha"]
        return not alpha.is_linked and alpha.default_value <= 0
    if node.bl_idname == "ShaderNodeAddShader":
        sides = [clear(s) or glows(s) for s in node.inputs]
        return all(sides) and any(clear(s) for s in node.inputs)
    return False


def glows(socket):
    """True when an Emission shader feeds `socket`."""
    return (
        socket.is_linked and socket.links[0].from_node.bl_idname == "ShaderNodeEmission"
    )


def see_through(material):
    """Why camera rays pass a material: "volume material" (surface unlinked, volume
    linked), "fully transparent material" (surface `clear`); None when they do not."""
    output = output_node(material.node_tree) if material.use_nodes else None
    if output is None or "Surface" not in output.inputs:
        return None
    volume = output.inputs.get("Volume")
    if not output.inputs["Surface"].is_linked:
        return "volume material" if volume is not None and volume.is_linked else None
    return "fully transparent material" if clear(output.inputs["Surface"]) else None


def in_layer(obj, getter):
    """An object's view-layer flag (holdout or indirect only, also from its collection);
    False for an object outside the view layer."""
    try:
        return getattr(obj, getter)(view_layer=bpy.context.view_layer)
    except (RuntimeError, TypeError):
        return False


def camera_rule(instance, transparent):
    """Why Cycles' camera rays do not see an instance (its object or its instancer):
    camera rays off, holdout, indirect only, every material see-through (`see_through`);
    None when they do."""
    evaluated = instance.object
    owners = [evaluated.original]
    if instance.is_instance and instance.parent is not None:
        owners.append(instance.parent.original)
    for owner in owners:
        if not owner.visible_camera:
            return "camera rays off"
        if owner.is_holdout or in_layer(owner, "holdout_get"):
            return "holdout"
        if in_layer(owner, "indirect_only_get"):
            return "indirect only"
    slots = [s.material for s in evaluated.material_slots if s.material is not None]
    reasons = {transparent.get(m.name_full) for m in slots}
    if slots and None not in reasons:
        return "volume material" if "volume material" in reasons else reasons.pop()
    return None


def copies(depsgraph, keep=False):
    """{key: {"source", "triangles", "matrices"}} over the depsgraph's instances of
    geometry with triangles that camera rays see, a key being base + (k,), k numbering
    a base's evaluated data; `source` is a mesh made at the key's first copy when `keep`.
    Also {base: k's} and {name: (type, reason)} of the geometry left out."""
    found = {}
    keys = {}
    bases = {}
    left = {}
    transparent = {m.name_full: see_through(m) for m in bpy.data.materials}
    for instance in depsgraph.object_instances:
        evaluated = instance.object
        if evaluated.type not in GEOMETRY:
            continue
        reason = camera_rule(instance, transparent)
        if reason is not None:
            left.setdefault(evaluated.original.name_full, (evaluated.type, reason))
            continue
        base = base_of(evaluated.original)
        pointer = (base, evaluated.data.as_pointer() if evaluated.data else 0)
        if pointer not in keys:
            count = triangles(evaluated)
            keys[pointer] = (None, 0)
            if count is None:
                left.setdefault(
                    evaluated.original.name_full, (evaluated.type, "no mesh")
                )
            elif count:
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
    return found, bases, left


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


def not_taken(depsgraph, left):
    """[{"name", "type", "reason"}] of what Cycles draws and the copies do not hold:
    objects of a type `copies` does not take, hair strands, a world volume, and the
    geometry `copies` left out (`left`), then the objects hidden in the render."""
    entries, named = [], set()

    def add(name, kind, reason):
        if name not in named:
            named.add(name)
            entries.append({"name": name, "type": kind, "reason": reason})

    drawn = set()
    for instance in depsgraph.object_instances:
        original = instance.object.original
        drawn.add(original.name_full)
        if instance.object.type in NOT_TAKEN:
            add(original.name_full, instance.object.type, "type not copied")
        for system in getattr(instance.object, "particle_systems", ()):
            hair = system.settings.type == "HAIR"
            if hair and system.settings.render_type == "PATH":
                add(original.name_full, "HAIR", "hair strands not copied")
    world = bpy.context.scene.world
    output = output_node(world.node_tree) if world and world.use_nodes else None
    if output is not None and output.inputs["Volume"].is_linked:
        add("world volume", "WORLD", "volume not copied")
    for name, (kind, reason) in sorted(left.items()):
        add(name, kind, reason)
    for obj in bpy.context.view_layer.objects:
        if obj.type in GEOMETRY and obj.name_full not in drawn:
            add(obj.name_full, obj.type, "hidden in the render")
    return entries


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
