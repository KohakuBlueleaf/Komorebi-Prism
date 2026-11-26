"""Helpers the export imports inside Blender: every material of the built copy rewritten
as a plain Principled BSDF the glTF exporter writes as it is (images kept, chains over
images baked in texture space, other shader trees mapped), and the record of each."""

import time

import bake
import bpy
import numpy
from graph import DEFAULT_UV, chain, coordinate, names, resolve
from shaders import PRINCIPLED, default_of, mapped

COLOUR = {"Base Color", "Emission Color"}
CONSTANT_ONLY = {"Emission Strength", "IOR"}
SOCKETS = (
    "Base Color",
    "Metallic",
    "Roughness",
    "Alpha",
    "Emission Color",
    "Emission Strength",
    "Transmission Weight",
    "IOR",
    "Normal",
)
SAME = 1e-4  # a baked result whose values lie within this of each other: one value
MASK_CUTOFF = 0.5
NORMAL_MAP = "ShaderNodeNormalMap"


def plain_image(path, out):
    """{"image", "output", "coord", ...} when `out` is an Image Texture's output on
    uv coordinates (through a Mapping node), else None."""
    node = out.node
    if node.bl_idname != "ShaderNodeTexImage" or node.projection != "FLAT":
        return None
    if node.image is None:
        return None
    space = coordinate(path, node.inputs["Vector"])
    if space[0] == "geometry":
        return None
    spec = {"image": node.image, "output": out.name, "coord": space[:2]}
    return spec | {"extension": node.extension, "interpolation": node.interpolation}


def as_is(path, out):
    """An image link the exporter reads as it is: an Image Texture, or one channel of
    it through a Separate Color node in RGB mode; else None."""
    found = plain_image(path, out)
    if found is not None:
        return found | {"channel": None}
    node = out.node
    if node.bl_idname == "ShaderNodeSeparateColor" and node.mode == "RGB":
        inner = resolve(path, node.inputs["Color"])
        if inner[0] == "out" and inner[2].name == "Color":
            found = plain_image(inner[1], inner[2])
            if found is not None:
                return found | {"channel": out.identifier}
    return None


def tiled(info):
    """True when an image of a chain holds several UDIM tiles (the quad covers one)."""
    images = [i.image for i in info["images"] if i.image is not None]
    return any(im.source == "TILED" and len(im.tiles) > 1 for im in images)


class Rewriter:
    """Chooses, bakes and rebuilds the materials; keeps the record and the seconds."""

    def __init__(self):
        self.baker = None
        self.record = {}

    def bake(self, material, path, out, info, colour, one_minus=False):
        """The chain at `out` baked over the uv square: ("constant", value) or
        ("image", spec); None when its leaves do not share one texture space."""
        coords = set(info["coords"])
        if len(coords) > 1:
            return None
        coord = coords.pop() if coords else (DEFAULT_UV, None)
        sizes = [tuple(i.image.size) for i in info["images"] if i.image is not None]
        width = min(max([s[0] for s in sizes] or [bake.NO_IMAGE_SIDE]), bake.MOST_SIDE)
        height = min(max([s[1] for s in sizes] or [bake.NO_IMAGE_SIDE]), bake.MOST_SIDE)
        if self.baker is None:
            self.baker = bake.Baker()
        for name in {c[0] for c in info["coords"]}:
            self.baker.uv_map(name)
        target = (names(path), out.node.name, out.identifier)
        mute = sorted(set(info["mute"]))
        values = self.baker.bake(
            material, target, (max(width, 1), max(height, 1)), mute, one_minus
        )
        rgb = values[..., :3].astype(numpy.float64)
        if numpy.all(rgb.max(axis=(0, 1)) - rgb.min(axis=(0, 1)) <= SAME):
            mean = rgb.mean(axis=(0, 1))
            return ("constant", (*mean, 1.0) if colour else float(mean.mean()))
        image = bake.byte_image(f"{material.name}_baked", rgb, colour)
        return ("image", baked_spec(image, coord, info))

    def mean(self, material, path, out, info, colour, fallback):
        """Class X for a socket: the mean of its chain on the quad when defined, else
        `fallback`."""
        if info["undefined"] is None:
            plain = dict(info, coords=[], mute=[])
            try:
                result = self.bake(material, path, out, plain, colour)
            except RuntimeError:
                result = None
            if result is not None:
                return mean_of(result, colour)
        return fallback

    def socket(self, material, name, src):
        """The choice for one Principled input: {"done", "value" | "spec", "node"}."""
        colour = name in COLOUR
        fallback = default_of(src)
        one_minus = src[0] == "one_minus"
        base = src[1] if one_minus else src
        if base[0] == "const":
            value = base[1]
            return {"done": "constant", "value": 1 - value if one_minus else value}
        found = resolve(base[1], base[2])
        if found[0] == "const":
            value = found[1]
            return {"done": "constant", "value": 1 - value if one_minus else value}
        _, path, out = found
        if name == "Normal":
            return self.normal(material, path, out)
        if not one_minus and name not in CONSTANT_ONLY:
            spec = as_is(path, out)
            if spec is not None:
                return {"done": "as_is", "spec": spec}
        info = chain(path, out)
        if info["geometry"] is None and tiled(info):
            cause = "UDIM tiles"
        elif info["geometry"] is None:
            result = self.bake(material, path, out, info, colour, one_minus)
            if result is not None and result[0] == "constant":
                return {"done": "constant", "value": result[1]}
            if result is not None and name not in CONSTANT_ONLY:
                return {"done": "baked", "spec": result[1]}
            if result is not None:
                value = mean_of(result, colour)
                return {"done": "lost", "value": value, "node": "constant only"}
            cause = "texture spaces differ"
        else:
            cause = info["geometry"]
        value = self.mean(material, path, out, info, colour, fallback)
        return {"done": "lost", "value": value, "node": cause}

    def normal(self, material, path, out):
        """The choice for the Normal input: a Normal Map over an image or a baked chain,
        a Bump's height baked and turned into a normal map, else lost."""
        node = out.node
        if node.bl_idname == NORMAL_MAP and node.space == "TANGENT":
            strength = resolve(path, node.inputs["Strength"])
            colour = resolve(path, node.inputs["Color"])
            if colour[0] == "const" or strength[0] != "const":
                return {"done": "lost", "node": NORMAL_MAP}
            spec = as_is(colour[1], colour[2])
            done = "as_is"
            if spec is None:
                info = chain(colour[1], colour[2])
                result = None
                if tiled(info):
                    return {"done": "lost", "node": "UDIM tiles"}
                if info["geometry"] is None:
                    result = self.bake(material, colour[1], colour[2], info, False)
                if result is None or result[0] == "constant":
                    return {"done": "lost", "node": info["geometry"] or NORMAL_MAP}
                spec, done = result[1], "baked"
            return {"done": done, "spec": spec, "strength": strength[1]}
        if node.bl_idname == "ShaderNodeBump":
            return self.bump(material, path, node)
        return {"done": "lost", "node": node.bl_idname}

    def bump(self, material, path, node):
        """A Bump node: its height chain baked and turned into a normal map."""
        inner = resolve(path, node.inputs["Normal"])
        if inner[0] == "out":
            kept = self.normal(material, inner[1], inner[2])
            return kept | {"done": "lost", "node": "ShaderNodeBump"}
        height = resolve(path, node.inputs["Height"])
        knobs = [resolve(path, node.inputs[k]) for k in ("Strength", "Distance")]
        if height[0] == "const":
            return {"done": "constant", "value": None}
        info = chain(height[1], height[2])
        if info["geometry"] is not None or any(k[0] != "const" for k in knobs):
            return {"done": "lost", "node": info["geometry"] or "ShaderNodeBump"}
        coords = set(info["coords"])
        if len(coords) > 1:
            return {"done": "lost", "node": "texture spaces differ"}
        if tiled(info):
            return {"done": "lost", "node": "UDIM tiles"}
        sizes = [tuple(i.image.size) for i in info["images"] if i.image is not None]
        width = min(max([s[0] for s in sizes] or [bake.NO_IMAGE_SIDE]), bake.MOST_SIDE)
        rows = min(max([s[1] for s in sizes] or [bake.NO_IMAGE_SIDE]), bake.MOST_SIDE)
        if self.baker is None:
            self.baker = bake.Baker()
        for name in {c[0] for c in info["coords"]}:
            self.baker.uv_map(name)
        target = (names(height[1]), height[2].node.name, height[2].identifier)
        mute = sorted(set(info["mute"]))
        values = self.baker.bake(material, target, (width, rows), mute)
        heights = values[..., :3].mean(axis=-1).astype(numpy.float64)
        normals = bake.normal_from_height(
            heights, knobs[0][1], knobs[1][1], getattr(node, "invert", False)
        )
        image = bake.byte_image(f"{material.name}_bump", normals * 0.5 + 0.5, False)
        coord = coords.pop() if coords else (DEFAULT_UV, None)
        return {"done": "bump", "spec": baked_spec(image, coord, info), "strength": 1.0}

    def rewrite(self, material):
        """Chooses for every input of one material, then rebuilds its tree; its record."""
        kind, sources, mode, cause = mapped(material)
        if kind == "X":
            choices = {
                "Base Color": {"done": "lost", "value": tuple(material.diffuse_color)}
            }
            choices["Base Color"]["node"] = cause
            sockets = {"Base Color": {"done": "lost", "node": cause}}
            build(material, choices, None)
            return {"class": "X", "node": cause, "sockets": sockets}
        choices = {}
        for name in SOCKETS:
            if name in sources:
                choices[name] = self.socket(material, name, sources[name])
        build(material, choices, mode)
        sockets = {
            name: {"done": p["done"]} | ({"node": p["node"]} if "node" in p else {})
            for name, p in choices.items()
        }
        return {"class": kind, "sockets": sockets}

    def run(self, materials):
        """Rewrites each material once; {name: record}, seconds and bakes."""
        started = time.perf_counter()
        for material in materials:
            if material.name_full in self.record:
                continue
            self.record[material.name_full] = self.rewrite(material)
        seconds = time.perf_counter() - started
        bakes = self.baker.count if self.baker else 0
        if self.baker is not None:
            self.baker.close()
        return self.record, round(seconds, 1), bakes


def mean_of(result, colour):
    """The mean of a bake's result (a constant, or an image removed after reading)."""
    if result[0] == "constant":
        return result[1]
    image = result[1]["image"]
    pixels = numpy.empty(image.size[0] * image.size[1] * 4, numpy.float32)
    image.pixels.foreach_get(pixels)
    bpy.data.images.remove(image)
    rgb = pixels.reshape(-1, 4)[:, :3].astype(numpy.float64)
    mean = (bake.decode_srgb(rgb) if colour else rgb).mean(axis=0)
    return (*mean, 1.0) if colour else float(mean.mean())


def baked_spec(image, coord, info):
    """The image spec of a baked chain: its texture space and the first leaf's
    extension."""
    extension = info["images"][0].extension if info["images"] else "REPEAT"
    spec = {"image": image, "output": "Color", "channel": None, "coord": coord}
    return spec | {"extension": extension, "interpolation": "Linear"}


def image_node(tree, spec):
    """An Image Texture node of `spec` with its uv map and Mapping; its output socket
    (one channel through a Separate Color node when the spec names one)."""
    texture = tree.nodes.new("ShaderNodeTexImage")
    texture.image = spec["image"]
    texture.extension = spec["extension"]
    texture.interpolation = spec["interpolation"]
    uv_name, mapping = spec["coord"]
    if uv_name:
        coordinates = tree.nodes.new("ShaderNodeUVMap")
        coordinates.uv_map = uv_name
        vector = coordinates.outputs["UV"]
    else:
        vector = tree.nodes.new("ShaderNodeTexCoord").outputs["UV"]
    if mapping is not None:
        moved = tree.nodes.new("ShaderNodeMapping")
        moved.vector_type = mapping[0]
        for key, value in zip(
            ("Location", "Rotation", "Scale"), mapping[1:], strict=True
        ):
            moved.inputs[key].default_value = value
        tree.links.new(vector, moved.inputs["Vector"])
        vector = moved.outputs["Vector"]
    tree.links.new(vector, texture.inputs["Vector"])
    out = texture.outputs[spec["output"]]
    if spec.get("channel"):
        split = tree.nodes.new("ShaderNodeSeparateColor")
        split.mode = "RGB"
        tree.links.new(out, split.inputs["Color"])
        out = next(s for s in split.outputs if s.identifier == spec["channel"])
    return out


def build(material, choices, mode):
    """Replaces a material's tree by an output and one Principled BSDF fed by `choices`."""
    tree = material.node_tree
    tree.nodes.clear()
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    output.target = "ALL"
    shader = tree.nodes.new(PRINCIPLED)
    tree.links.new(shader.outputs[0], output.inputs["Surface"])
    for name, choice in choices.items():
        socket = shader.inputs[name]
        if "spec" in choice:
            out = image_node(tree, choice["spec"])
            if name == "Normal":
                normal = tree.nodes.new(NORMAL_MAP)
                normal.uv_map = choice["spec"]["coord"][0]
                normal.inputs["Strength"].default_value = choice.get("strength", 1.0)
                tree.links.new(out, normal.inputs["Color"])
                out = normal.outputs["Normal"]
            elif name == "Alpha" and mode == "MASK":
                out = mask(tree, out)
            tree.links.new(out, socket)
        elif choice.get("value") is not None and name != "Normal":
            value = choice["value"]
            if hasattr(socket.default_value, "__len__"):
                width = len(socket.default_value)
                value = tuple(value)[:width] + (1.0,) * (width - len(tuple(value)))
            elif hasattr(value, "__len__"):
                value = float(numpy.mean(value[:3]))
            socket.default_value = value


def mask(tree, out):
    """Alpha clipped at MASK_CUTOFF in the form the exporter reads as MASK."""
    below = tree.nodes.new("ShaderNodeMath")
    below.operation = "LESS_THAN"
    below.inputs[1].default_value = MASK_CUTOFF
    tree.links.new(out, below.inputs[0])
    flip = tree.nodes.new("ShaderNodeMath")
    flip.operation = "SUBTRACT"
    flip.inputs[0].default_value = 1.0
    tree.links.new(below.outputs[0], flip.inputs[1])
    return flip.outputs[0]


def used(found):
    """The materials of the copies' meshes, in a fixed order; a material of a library
    is replaced in those meshes by a local copy of the same name (this session only)."""
    seen, local = {}, {}
    for key in sorted(found):
        mesh = found[key]["source"]
        for i, material in enumerate(mesh.materials if mesh is not None else ()):
            if material is None or material.node_tree is None:
                continue
            if material.library is not None:
                if material.name_full not in local:
                    copy = material.copy()
                    copy.name = material.name
                    local[material.name_full] = copy
                material = local[material.name_full]
                mesh.materials[i] = material
            seen.setdefault(material.name_full, material)
    return list(seen.values())
