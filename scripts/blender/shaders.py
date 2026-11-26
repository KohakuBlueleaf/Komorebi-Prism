"""Helpers the export imports inside Blender: a material's surface shader found through
reroutes and groups, and a tree of other shaders mapped onto the inputs of one Principled
BSDF (each input a constant, an input socket to walk, or 1 - one)."""

from graph import resolve, value_of

PRINCIPLED = "ShaderNodeBsdfPrincipled"
DIFFUSE = {"ShaderNodeBsdfDiffuse", "ShaderNodeBsdfTranslucent"}
GLOSSY = {"ShaderNodeBsdfAnisotropic", "ShaderNodeBsdfGlossy"}
GLASS = {"ShaderNodeBsdfGlass", "ShaderNodeBsdfRefraction"}
FRESNEL = {"ShaderNodeFresnel", "ShaderNodeLayerWeight"}
THRESHOLD_OPERATIONS = {"GREATER_THAN", "LESS_THAN", "ROUND", "COMPARE"}
TINT = 0.05  # channels further apart than this: a tinted colour


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


def mixed(path, node):
    """A Mix Shader or Add Shader reduced by the rule's rows."""
    adding = node.bl_idname == "ShaderNodeAddShader"
    first = side(path, node.inputs[0 if adding else 1])
    second = side(path, node.inputs[1 if adding else 2])
    fac = ("const", 0.5) if adding else source(path, node, "Fac")
    kinds = {first["kind"], second["kind"]}
    constant = constant_of(fac)
    if not adding and constant in (0.0, 1.0):
        return second if constant == 1.0 else first
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
