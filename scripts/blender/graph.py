"""Helpers the export imports inside Blender: walking a material's node tree through
reroutes, muted nodes and groups, and the leaves of a chain of nodes."""

ROUND = 6
PURE = {
    "ShaderNodeMix",
    "ShaderNodeMixRGB",
    "ShaderNodeValToRGB",
    "ShaderNodeHueSaturation",
    "ShaderNodeRGBCurve",
    "ShaderNodeFloatCurve",
    "ShaderNodeVectorCurve",
    "ShaderNodeMath",
    "ShaderNodeVectorMath",
    "ShaderNodeInvert",
    "ShaderNodeGamma",
    "ShaderNodeBrightContrast",
    "ShaderNodeClamp",
    "ShaderNodeMapRange",
    "ShaderNodeSeparateColor",
    "ShaderNodeCombineColor",
    "ShaderNodeSeparateRGB",
    "ShaderNodeCombineRGB",
    "ShaderNodeSeparateHSV",
    "ShaderNodeCombineHSV",
    "ShaderNodeSeparateXYZ",
    "ShaderNodeCombineXYZ",
    "ShaderNodeRGBToBW",
    "ShaderNodeBlackbody",
    "ShaderNodeWavelength",
    "ShaderNodeVectorRotate",
}
CONSTANT = {"ShaderNodeRGB", "ShaderNodeValue"}
PROCEDURAL = {
    "ShaderNodeTexNoise",
    "ShaderNodeTexVoronoi",
    "ShaderNodeTexWave",
    "ShaderNodeTexGradient",
    "ShaderNodeTexMagic",
    "ShaderNodeTexBrick",
    "ShaderNodeTexChecker",
    "ShaderNodeTexWhiteNoise",
    "ShaderNodeTexMusgrave",
    "ShaderNodeTexGabor",
}
# Nodes whose value depends on the ray or the view: no mean is taken on a quad.
UNDEFINED_ON_QUAD = {
    "ShaderNodeLightPath",
    "ShaderNodeCameraData",
    "ShaderNodeLightFalloff",
    "ShaderNodeParticleInfo",
    "ShaderNodePointInfo",
    "ShaderNodeHairInfo",
    "ShaderNodeUVAlongStroke",
}
DEFAULT_UV = ""  # the active render uv map


def value_of(socket):
    """A socket's own value as a float or a tuple; None for a shader socket."""
    value = getattr(socket, "default_value", None)
    if value is None:
        return None
    if hasattr(value, "__len__"):
        return tuple(float(v) for v in value)
    return float(value)


def link_of(socket):
    """The first valid, unmuted link into an input socket, or None."""
    if not socket.is_linked:
        return None
    for link in socket.links:
        if link.is_valid and not link.is_muted:
            return link
    return None


def group_output(tree):
    """The active group output node of a group's tree, or None."""
    outputs = [n for n in tree.nodes if n.bl_idname == "NodeGroupOutput"]
    return next(
        (n for n in outputs if n.is_active_output), outputs[0] if outputs else None
    )


def by_identifier(sockets, identifier):
    """The socket of `sockets` with `identifier`, or None."""
    return next((s for s in sockets if s.identifier == identifier), None)


def resolve(path, socket):
    """What feeds an input socket at `path` (group nodes from the top), through reroutes,
    muted nodes and groups: ("const", value) or ("out", path, output socket)."""
    path = tuple(path)
    for _ in range(10000):
        link = link_of(socket)
        if link is None:
            return ("const", value_of(socket))
        node, out = link.from_node, link.from_socket
        if node.mute:
            inner = next((i for i in node.internal_links if i.to_socket == out), None)
            if inner is None:
                return ("const", value_of(socket))
            socket = inner.from_socket
        elif node.bl_idname == "NodeReroute":
            socket = node.inputs[0]
        elif node.bl_idname == "ShaderNodeGroup":
            output = group_output(node.node_tree) if node.node_tree else None
            entry = by_identifier(output.inputs, out.identifier) if output else None
            if entry is None:
                return ("const", value_of(socket))
            path, socket = path + (node,), entry
        elif node.bl_idname == "NodeGroupInput":
            entry = by_identifier(path[-1].inputs, out.identifier) if path else None
            if entry is None:
                return ("const", value_of(socket))
            path, socket = path[:-1], entry
        else:
            return ("out", path, out)
    raise ValueError("node tree: a cycle of reroutes or groups")


def names(path):
    """A path of group nodes as their names."""
    return tuple(n.name for n in path)


def coordinate(path, socket):
    """The texture space of a Vector input: (uv map, mapping key, mapping node ref or
    None), or ("geometry", node type) when it depends on the geometry."""
    found = resolve(path, socket)
    if found[0] == "const":
        return (
            (DEFAULT_UV, None, None) if not socket.is_linked else ("geometry", "value")
        )
    _, at, out = found
    node = out.node
    if node.bl_idname == "ShaderNodeUVMap":
        return (node.uv_map, None, None)
    if node.bl_idname == "ShaderNodeTexCoord" and out.name == "UV":
        return (DEFAULT_UV, None, None)
    if node.bl_idname == "ShaderNodeMapping":
        params = [
            resolve(at, node.inputs[k]) for k in ("Location", "Rotation", "Scale")
        ]
        if any(p[0] != "const" for p in params) or "Location" not in node.inputs:
            return ("geometry", "ShaderNodeMapping")
        if not node.inputs["Vector"].is_linked:
            return ("geometry", "ShaderNodeMapping")
        inner = coordinate(at, node.inputs["Vector"])
        if inner[0] == "geometry":
            return inner
        if inner[1] is not None:
            return ("geometry", "ShaderNodeMapping")
        rounded = tuple(tuple(round(v, ROUND) for v in p[1]) for p in params)
        key = (node.vector_type, *rounded)
        return (inner[0], key, (names(at), node.name))
    return ("geometry", node.bl_idname)


def chain(path, out):
    """The leaves of the chain feeding output socket `out`: {"images", "coords",
    "mute", "geometry" (the first node depending on the geometry, or None),
    "undefined" (a node with no value on a quad)}."""
    info = {"images": [], "coords": [], "mute": [], "geometry": None, "undefined": None}
    seen, stack = set(), [(tuple(path), out)]
    while stack:
        at, socket = stack.pop()
        node = socket.node
        key = (names(at), node.name)
        if key in seen:
            continue
        seen.add(key)
        kind = node.bl_idname
        inputs = list(node.inputs)
        if kind == "ShaderNodeTexImage" or kind in PROCEDURAL:
            space = coordinate(at, node.inputs["Vector"])
            flat = kind != "ShaderNodeTexImage" or node.projection == "FLAT"
            if not flat:
                info["geometry"] = info["geometry"] or kind
            elif space[0] == "geometry":
                info["geometry"] = info["geometry"] or space[1]
            else:
                info["coords"].append(space[:2])
                if space[2] is not None:
                    info["mute"].append(space[2])
            if kind == "ShaderNodeTexImage":
                info["images"].append(node)
            inputs = [s for s in inputs if s.name != "Vector"]
        elif kind in ("ShaderNodeUVMap", "ShaderNodeTexCoord", "ShaderNodeMapping"):
            space = coordinate(at, _Probe(socket))
            if space[0] == "geometry":
                info["geometry"] = info["geometry"] or space[1]
            else:
                info["coords"].append(space[:2])
                if space[2] is not None:
                    info["mute"].append(space[2])
            continue
        elif kind in CONSTANT:
            continue
        elif kind not in PURE:
            info["geometry"] = info["geometry"] or kind
            if kind in UNDEFINED_ON_QUAD:
                info["undefined"] = info["undefined"] or kind
        for entry in inputs:
            found = resolve(at, entry)
            if found[0] == "out":
                stack.append((found[1], found[2]))
    return info


class _Probe:
    """A stand-in input socket linked to one output (for `coordinate`)."""

    def __init__(self, out):
        self.is_linked = True
        self.links = [_ProbeLink(out)]


class _ProbeLink:
    """A link from `out`, valid and unmuted."""

    def __init__(self, out):
        self.from_node, self.from_socket = out.node, out
        self.is_valid, self.is_muted = True, False
