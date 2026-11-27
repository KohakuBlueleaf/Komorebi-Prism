"""Helpers the export imports inside Blender: a material's surface shader found through
reroutes and groups, and a tree of other shaders mapped onto the inputs of one Principled
BSDF (each input a constant, an input socket to walk, or 1 - one)."""

import bake
from graph import names, resolve, value_of

PRINCIPLED = "ShaderNodeBsdfPrincipled"
DIFFUSE = {"ShaderNodeBsdfDiffuse", "ShaderNodeBsdfTranslucent"}
GLOSSY = {"ShaderNodeBsdfAnisotropic", "ShaderNodeBsdfGlossy"}
GLASS = {"ShaderNodeBsdfGlass", "ShaderNodeBsdfRefraction"}
FRESNEL = {"ShaderNodeFresnel", "ShaderNodeLayerWeight"}
THRESHOLD_OPERATIONS = {"GREATER_THAN", "LESS_THAN", "ROUND", "COMPARE"}
TINT = 0.05  # channels further apart than this: a tinted colour
# Light Path outputs for a ray from the camera; Ray Length has no constant.
CAMERA_RAY = {
    "Is Camera Ray": 1.0,
    "Is Shadow Ray": 0.0,
    "Is Diffuse Ray": 0.0,
    "Is Glossy Ray": 0.0,
    "Is Singular Ray": 0.0,
    "Is Reflection Ray": 0.0,
    "Is Transmission Ray": 0.0,
    "Is Volume Scatter Ray": 0.0,
    "Ray Depth": 0.0,
    "Diffuse Depth": 0.0,
    "Glossy Depth": 0.0,
    "Transparent Depth": 0.0,
    "Transmission Depth": 0.0,
}
MATH = {
    "ADD": lambda a, b: a + b,
    "SUBTRACT": lambda a, b: a - b,
    "MULTIPLY": lambda a, b: a * b,
    "DIVIDE": lambda a, b: a / b if b != 0 else 0.0,
    "MAXIMUM": max,
    "MINIMUM": min,
    "GREATER_THAN": lambda a, b: float(a > b),
    "LESS_THAN": lambda a, b: float(a < b),
}
MIXED_TYPE = {"Base Color": "RGBA", "Emission Color": "RGBA", "Normal": "VECTOR"}
MIX_SOCKETS = {"RGBA": "Color", "VECTOR": "Vector", "FLOAT": "Float"}
_EXPOSED = {}  # top tree pointer: the group copies made to bring sockets out


class NotCovered(Exception):
    """A shader tree the mapping does not cover; carries the node type."""


def source(path, node, name):
    """An input of a node as a source to walk."""
    return ("input", tuple(path), node.inputs[name])


def surface_shader(material):
    """("out", path, output socket) of the shader feeding the active output's Surface,
    or None."""
    tree = material.node_tree if material.use_nodes else None
    output = None
    for target in ("ALL", "CYCLES", "EEVEE"):
        output = output or (tree.get_output_node(target) if tree else None)
    if output is None or output.inputs.get("Surface") is None:
        return None
    found = resolve((), output.inputs["Surface"])
    return found if found[0] == "out" else None


def principled_inputs(path, node):
    """Every mapped input of a Principled BSDF as a source."""
    return {
        name: source(path, node, name)
        for name in (
            "Base Color",
            "Metallic",
            "Roughness",
            "Alpha",
            "Normal",
            "Emission Color",
            "Emission Strength",
            "Transmission Weight",
            "IOR",
            "Sheen Weight",
            "Sheen Tint",
            "Sheen Roughness",
        )
    }


def constant_of(src):
    """The constant a source resolves to, or None."""
    if src[0] == "const":
        return src[1]
    if src[0] == "input":
        found = resolve(src[1], src[2])
        return found[1] if found[0] == "const" else None
    return None


def tinted(src):
    """True when a colour source is linked or its channels differ by more than TINT."""
    value = constant_of(src)
    if value is None:
        return True
    return max(value[:3]) - min(value[:3]) > TINT


def mask_factor(src):
    """True when a factor source is an image's alpha or a threshold."""
    if src[0] != "input":
        return False
    found = resolve(src[1], src[2])
    if found[0] != "out":
        return False
    node, out = found[2].node, found[2]
    if node.bl_idname == "ShaderNodeTexImage" and out.name == "Alpha":
        return True
    if node.bl_idname == "ShaderNodeMath":
        return node.operation in THRESHOLD_OPERATIONS
    if node.bl_idname == "ShaderNodeValToRGB":
        return node.color_ramp.interpolation == "CONSTANT"
    return False


def scalar(value):
    """A constant as one number (the mean of a colour's channels)."""
    if hasattr(value, "__len__"):
        return sum(value[:3]) / len(value[:3])
    return value


def camera_value(found):
    """The value a resolved output takes for a ray from the camera (Light Path outputs
    through Math nodes), or None."""
    if found[0] == "const":
        return None if found[1] is None else scalar(found[1])
    _, path, out = found
    node = out.node
    if node.bl_idname == "ShaderNodeLightPath":
        return CAMERA_RAY.get(out.name)
    if node.bl_idname != "ShaderNodeMath" or node.operation not in MATH:
        return None
    values = [camera_value(resolve(path, s)) for s in list(node.inputs)[:2]]
    if None in values:
        return None
    value = MATH[node.operation](*values)
    return min(max(value, 0.0), 1.0) if node.use_clamp else value


def camera_constant(src):
    """A factor source's value for a ray from the camera, or None."""
    value = constant_of(src)
    if value is not None or src[0] != "input":
        return value
    return camera_value(resolve(src[1], src[2]))


def fresnel_factor(src):
    """True when a factor source is a Fresnel or Layer Weight node."""
    if src[0] != "input":
        return False
    found = resolve(src[1], src[2])
    return found[0] == "out" and found[2].node.bl_idname in FRESNEL


def layer(path, out):
    """One shader output reduced to {"kind", input name: source}; NotCovered when the
    rule has no row for it."""
    node = out.node
    kind = node.bl_idname
    if kind == PRINCIPLED:
        return {"kind": "principled"} | principled_inputs(path, node)
    if kind in DIFFUSE:
        return {
            "kind": "diffuse",
            "Base Color": source(path, node, "Color"),
            "Roughness": ("const", 1.0),
            "Normal": source(path, node, "Normal"),
        }
    if kind in GLOSSY:
        return {
            "kind": "glossy",
            "Base Color": source(path, node, "Color"),
            "Roughness": source(path, node, "Roughness"),
            "Normal": source(path, node, "Normal"),
        }
    if kind in GLASS:
        return {
            "kind": "glass",
            "Base Color": source(path, node, "Color"),
            "Roughness": source(path, node, "Roughness"),
            "IOR": source(path, node, "IOR"),
            "Normal": source(path, node, "Normal"),
            "Transmission Weight": ("const", 1.0),
        }
    if kind == "ShaderNodeBsdfTransparent":
        return {"kind": "transparent"}
    if kind == "ShaderNodeEmission":
        return {
            "kind": "emission",
            "Base Color": ("const", (0.0, 0.0, 0.0, 1.0)),
            "Emission Color": source(path, node, "Color"),
            "Emission Strength": source(path, node, "Strength"),
        }
    if kind in ("ShaderNodeMixShader", "ShaderNodeAddShader"):
        return mixed(path, node)
    raise NotCovered(kind)


def side(path, socket):
    """The layer feeding one shader input of a mix."""
    found = resolve(path, socket)
    if found[0] != "out":
        raise NotCovered("unlinked shader input")
    return layer(found[1], found[2])


def top_socket(tree, src):
    """(output socket at the top of `tree`, None) giving a source, or (None, value) for a
    constant; a socket inside groups is brought out through new group outputs."""
    if src[0] == "const":
        return None, src[1]
    if src[0] == "one_minus":
        inner, value = top_socket(tree, src[1])
        if inner is None:
            return None, None if value is None else 1 - scalar(value)
        flip = tree.nodes.new("ShaderNodeMath")
        flip.operation = "SUBTRACT"
        flip.inputs[0].default_value = 1.0
        tree.links.new(inner, flip.inputs[1])
        return flip.outputs[0], None
    found = resolve(src[1], src[2])
    if found[0] == "const":
        return None, found[1]
    _, path, out = found
    if not path:
        return out, None
    cache = _EXPOSED.setdefault(tree.as_pointer(), {(): tree})
    target = (names(path), out.node.name, out.identifier)
    return bake.expose(None, target, cache), None


def feed(tree, socket, src):
    """Links a source into an input socket of a new node, or sets its constant."""
    out, value = top_socket(tree, src)
    if out is not None:
        tree.links.new(out, socket)
    elif value is not None:
        width = (
            len(socket.default_value) if hasattr(socket.default_value, "__len__") else 0
        )
        if width and not hasattr(value, "__len__"):
            value = (value,) * min(width, 3) + (1.0,) * (width - 3)
        elif width:
            value = tuple(value)[:width] + (1.0,) * (width - len(tuple(value)))
        elif hasattr(value, "__len__"):
            value = scalar(value)
        socket.default_value = value


def mix_of(tree, name, fac, a, b):
    """A source mixing two sources by a factor (a Mix node made at the top of `tree`)."""
    kind = MIXED_TYPE.get(name, "FLOAT")
    node = tree.nodes.new("ShaderNodeMix")
    node.data_type = kind
    node.clamp_factor = True
    suffix = MIX_SOCKETS[kind]
    entries = {s.identifier: s for s in node.inputs}
    feed(tree, entries["Factor_Float"], fac)
    feed(tree, entries[f"A_{suffix}"], a)
    feed(tree, entries[f"B_{suffix}"], b)
    out = next(s for s in node.outputs if s.identifier == f"Result_{suffix}")
    holder = tree.nodes.new("NodeReroute")
    tree.links.new(out, holder.inputs[0])
    return ("input", (), holder.inputs[0])


def principled_mix(path, node, fac, first, second):
    """Two Principled BSDFs mixed: each input the mix of the two by the factor; the
    normal the side's that is linked, mixed only when both are."""
    tree = (path[0] if path else node).id_data
    out = {"kind": "principled"}
    for name in first.keys() - {"kind", "alpha_mode"}:
        a, b = first[name], second.get(name, first[name])
        if name == "Normal" and (constant_of(a) is None) != (constant_of(b) is None):
            out[name] = a if constant_of(b) is not None else b
        elif constant_of(a) is not None and constant_of(a) == constant_of(b):
            out[name] = a
        else:
            out[name] = mix_of(tree, name, fac, a, b)
    return out


def mixed(path, node):
    """A Mix Shader or Add Shader reduced by the rule's rows."""
    adding = node.bl_idname == "ShaderNodeAddShader"
    inputs = [node.inputs[0], node.inputs[1]] if adding else node.inputs[1:3]
    fac = ("const", 0.5) if adding else source(path, node, "Fac")
    constant = constant_of(fac)
    if constant is None and not adding:
        constant = camera_constant(fac)
        fac = fac if constant is None else ("const", constant)
    if not adding and constant in (0.0, 1.0):
        return side(path, inputs[1 if constant == 1.0 else 0])
    linked = [resolve(path, s)[0] == "out" for s in inputs]
    if linked.count(True) == 1:
        return side(path, inputs[linked.index(True)])
    first, second = side(path, inputs[0]), side(path, inputs[1])
    kinds = {first["kind"], second["kind"]}
    if "transparent" in kinds and len(kinds) == 2 and not adding:
        shown = second if first["kind"] == "transparent" else first
        if constant_of(shown.get("Alpha", ("const", 1.0))) != 1.0:
            raise NotCovered("ShaderNodeMixShader")
        alpha = fac if first["kind"] == "transparent" else ("one_minus", fac)
        mode = "MASK" if mask_factor(fac) else "BLEND"
        return shown | {"Alpha": alpha, "alpha_mode": mode}
    if "emission" in kinds and len(kinds) == 2:
        glow = first if first["kind"] == "emission" else second
        rest = second if glow is first else first
        return rest | {k: glow[k] for k in ("Emission Color", "Emission Strength")}
    if kinds == {"principled", "diffuse"}:
        return first if first["kind"] == "principled" else second
    if kinds == {"principled"} and not adding:
        return principled_mix(path, node, fac, first, second)
    if kinds == {"glass", "glossy"}:
        return first if first["kind"] == "glass" else second
    if kinds == {"diffuse", "glossy"}:
        diffuse = first if first["kind"] == "diffuse" else second
        glossy = second if diffuse is first else first
        weight = (
            constant
            if glossy is second
            else (None if constant is None else 1 - constant)
        )
        dielectric = (
            adding or fresnel_factor(fac) or (weight is not None and weight < 0.5)
        )
        if not dielectric and tinted(glossy["Base Color"]):
            return glossy | {"kind": "glossy", "Metallic": ("const", 1.0)}
        normal = diffuse["Normal"]
        if constant_of(normal) is not None and constant_of(glossy["Normal"]) is None:
            normal = glossy["Normal"]
        return (
            diffuse
            | {"kind": "diffuse", "Roughness": glossy["Roughness"]}
            | {"Normal": normal}
        )
    raise NotCovered(node.bl_idname)


def mapped(material):
    """(class, {input name: source} or None, alpha mode or None, cause or None) of a
    material: P for a Principled BSDF, S for a tree the rule maps, X otherwise."""
    found = surface_shader(material)
    if found is None:
        return "X", None, None, "no surface shader"
    _, path, out = found
    if out.node.bl_idname == PRINCIPLED:
        return "P", principled_inputs(path, out.node), None, None
    try:
        reduced = layer(path, out)
    except NotCovered as refusal:
        return "X", None, None, str(refusal)
    if reduced["kind"] == "transparent":
        return "X", None, None, "ShaderNodeBsdfTransparent"
    if reduced["kind"] == "glossy" and "Metallic" not in reduced:
        reduced["Metallic"] = ("const", 1.0)
    reduced.setdefault("Metallic", ("const", 0.0))
    mode = reduced.pop("alpha_mode", None)
    reduced.pop("kind")
    return "S", reduced, mode, None


def default_of(src):
    """The value a source's socket holds itself (its default when linked)."""
    if src[0] == "input":
        return value_of(src[2])
    if src[0] == "const":
        return src[1]
    value = default_of(src[1])
    return None if value is None else 1 - value
