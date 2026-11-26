"""Helpers the export imports inside Blender: a socket of a material's node tree baked in
texture space on a unit quad by Cycles' bake of its emission, and a height turned into a
tangent-space normal map."""

import time

import bpy
import numpy

MOST_SIDE = 4096
NO_IMAGE_SIDE = 8
DEFAULT_UV = "UVMap"
INTERFACE = {"RGBA": "NodeSocketColor", "VECTOR": "NodeSocketVector"}


def encode_srgb(linear):
    """Linear values in [0, 1] encoded with the standard sRGB transfer."""
    c = numpy.clip(linear, 0.0, 1.0)
    return numpy.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def decode_srgb(encoded):
    """The standard sRGB transfer undone."""
    c = numpy.asarray(encoded, dtype=numpy.float64)
    return numpy.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def normal_from_height(height, strength, distance, invert=False):
    """(H, W) heights over the unit uv square, row 0 at v = 0, as (H, W, 3) unit
    tangent-space normals: central differences repeating at the edges."""
    rows, columns = height.shape
    d = -distance if invert else distance
    du = (numpy.roll(height, -1, 1) - numpy.roll(height, 1, 1)) * (columns / 2)
    dv = (numpy.roll(height, -1, 0) - numpy.roll(height, 1, 0)) * (rows / 2)
    bent = numpy.stack([-d * du, -d * dv, numpy.ones_like(height)], -1)
    bent /= numpy.linalg.norm(bent, axis=-1, keepdims=True)
    s = max(float(strength), 0.0)
    mixed = s * bent + (1 - s) * numpy.array([0.0, 0.0, 1.0])
    length = numpy.linalg.norm(mixed, axis=-1, keepdims=True)
    return mixed / numpy.where(length > 0, length, 1.0)


def byte_image(name, values, colour):
    """A packed 8-bit image of (H, W, 3 or 4) values in [0, 1], rows from v = 0: sRGB
    (encoded here) when `colour`, else non-colour data."""
    rows, columns = values.shape[:2]
    image = bpy.data.images.new(name, columns, rows, alpha=True)
    image.colorspace_settings.name = "sRGB" if colour else "Non-Color"
    rgba = numpy.ones((rows, columns, 4), numpy.float32)
    rgba[..., : values.shape[2]] = values[..., :4]
    if colour:
        rgba[..., :3] = encode_srgb(rgba[..., :3])
    image.pixels.foreach_set(
        (numpy.rint(rgba * 255) / 255).astype(numpy.float32).ravel()
    )
    image.pack()
    return image


def select_devices(scene):
    """Cycles on the GPU (OptiX, else CUDA) when one is present, else the CPU."""
    preferences = bpy.context.preferences.addons["cycles"].preferences
    for kind in ("OPTIX", "CUDA"):
        try:
            preferences.compute_device_type = kind
        except TypeError:
            continue
        preferences.get_devices()
        devices = [d for d in preferences.devices if d.type == kind]
        if devices:
            for device in preferences.devices:
                device.use = device.type == kind
            scene.cycles.device = "GPU"
            return kind
    scene.cycles.device = "CPU"
    return "CPU"


class Baker:
    """A scene holding a unit quad (uv = xy) baked by Cycles, one sample, no denoiser."""

    def __init__(self):
        self.scene = bpy.data.scenes.new("prism_bake")
        self.scene.render.engine = "CYCLES"
        self.scene.cycles.samples = 1
        self.scene.cycles.use_denoising = False
        self.device = select_devices(self.scene)
        mesh = bpy.data.meshes.new("prism_bake_quad")
        mesh.from_pydata(
            [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [], [(0, 1, 2, 3)]
        )
        self.quad = bpy.data.objects.new("prism_bake_quad", mesh)
        self.scene.collection.objects.link(self.quad)
        self.uv_map(DEFAULT_UV)
        self.seconds, self.count = 0.0, 0
        self.made, self.groups = [], set()

    def uv_map(self, name):
        """Gives the quad a uv layer `name` holding the unit square."""
        mesh = self.quad.data
        if name and mesh.uv_layers.get(name) is None:
            layer = mesh.uv_layers.new(name=name)
            for loop, corner in zip(layer.data, mesh.loops, strict=True):
                loop.uv = mesh.vertices[corner.vertex_index].co.xy

    def bake(self, material, target, size, mute=(), one_minus=False):
        """The (H, W, 4) linear values of `target` (path of group node names, node
        name, output identifier) of `material` over the unit square at size (W, H);
        Mapping nodes `mute` (path, name) passed through, 1 - the value when asked."""
        started = time.perf_counter()
        work = material.copy()
        cache = {(): work.node_tree}
        image = None
        try:
            tree = work.node_tree
            socket = expose(work, target, cache)
            for path, name in mute:
                writable(work, path, cache).nodes[name].mute = True
            if one_minus:
                inverse = tree.nodes.new("ShaderNodeMath")
                inverse.operation = "SUBTRACT"
                inverse.inputs[0].default_value = 1.0
                tree.links.new(socket, inverse.inputs[1])
                socket = inverse.outputs[0]
            emission = tree.nodes.new("ShaderNodeEmission")
            emission.inputs["Strength"].default_value = 1.0
            tree.links.new(socket, emission.inputs["Color"])
            for node in tree.nodes:
                if node.bl_idname == "ShaderNodeOutputMaterial":
                    node.is_active_output = False
            output = tree.nodes.new("ShaderNodeOutputMaterial")
            output.target = "ALL"
            tree.links.new(emission.outputs[0], output.inputs["Surface"])
            output.is_active_output = True
            width, height = size
            image = bpy.data.images.new("prism_bake", width, height, float_buffer=True)
            image.colorspace_settings.name = "Non-Color"
            holder = tree.nodes.new("ShaderNodeTexImage")
            holder.image = image
            tree.nodes.active = holder
            self.quad.data.materials.clear()
            self.quad.data.materials.append(work)
            self.run()
            pixels = numpy.empty(width * height * 4, numpy.float32)
            image.pixels.foreach_get(pixels)
            return pixels.reshape(height, width, 4)
        finally:
            self.quad.data.materials.clear()
            if image is not None:
                bpy.data.images.remove(image)
            self.made.append(work)
            self.groups.update(t.as_pointer() for path, t in cache.items() if path)
            self.seconds += time.perf_counter() - started
            self.count += 1

    def close(self):
        """Removes the bake scene, its quad and every material and group copy made."""
        bpy.data.scenes.remove(self.scene)
        mesh = self.quad.data
        bpy.data.objects.remove(self.quad)
        bpy.data.meshes.remove(mesh)
        for material in self.made:
            bpy.data.materials.remove(material)
        for tree in [t for t in bpy.data.node_groups if t.as_pointer() in self.groups]:
            bpy.data.node_groups.remove(tree)

    def run(self):
        """Cycles' bake of the emission on the quad, in the bake scene."""
        window = bpy.context.window
        previous = window.scene
        window.scene = self.scene
        try:
            layer = self.scene.view_layers[0]
            for obj in layer.objects:
                obj.select_set(obj == self.quad)
            layer.objects.active = self.quad
            bpy.ops.object.bake(type="EMIT", margin=0, use_clear=True)
        finally:
            window.scene = previous


def writable(material, path, cache):
    """The node tree at `path` (group node names from the top) of a material copy, its
    group trees copied along the path (once each)."""
    path = tuple(path)
    if path in cache:
        return cache[path]
    parent = writable(material, path[:-1], cache)
    group = parent.nodes[path[-1]]
    group.node_tree = group.node_tree.copy()
    cache[path] = group.node_tree
    return group.node_tree


def expose(material, target, cache):
    """The output socket `target` (path, node name, output identifier) brought to the
    top tree of a material copy through new outputs of the groups on its path."""
    path, name, identifier = target
    path = tuple(path)
    tree = writable(material, path, cache)
    socket = next(s for s in tree.nodes[name].outputs if s.identifier == identifier)
    for depth in range(len(path), 0, -1):
        tree = writable(material, path[:depth], cache)
        kind = INTERFACE.get(socket.type, "NodeSocketFloat")
        item = tree.interface.new_socket(
            "prism_bake", in_out="OUTPUT", socket_type=kind
        )
        out = next(
            (
                n
                for n in tree.nodes
                if n.bl_idname == "NodeGroupOutput" and n.is_active_output
            ),
            None,
        ) or tree.nodes.new("NodeGroupOutput")
        entry = next(s for s in out.inputs if s.identifier == item.identifier)
        tree.links.new(socket, entry)
        group = writable(material, path[: depth - 1], cache).nodes[path[depth - 1]]
        socket = next(s for s in group.outputs if s.identifier == item.identifier)
    return socket
