"""Run inside Blender on an empty file: the material rewrite on made materials against
values computed here; one JSON line with `ok`.
`blender --background --factory-startup --python selftest_materials.py`"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bake
import bpy
import common
import materials
import numpy

SIDE = 4
STEP = 1 / 255
PLAIN = {
    "ShaderNodeOutputMaterial",
    "ShaderNodeBsdfPrincipled",
    "ShaderNodeTexImage",
    "ShaderNodeTexCoord",
    "ShaderNodeUVMap",
    "ShaderNodeMapping",
    "ShaderNodeSeparateColor",
    "ShaderNodeNormalMap",
    "ShaderNodeMath",
}
RAMP_END = (1.0, 0.5, 0.25, 1.0)
BUMP_STRENGTH, BUMP_DISTANCE = 1.0, 0.1
RESULTS = []


def same(case, got, want, tolerance=0.0):
    """Records whether `got` equals `want` within `tolerance`."""
    g, w = numpy.asarray(got), numpy.asarray(want)
    if g.dtype.kind in "fiu" and w.dtype.kind in "fiu":
        equal = g.shape == w.shape and bool(numpy.all(numpy.abs(g - w) <= tolerance))
    else:
        equal = bool(numpy.array_equal(g, w))
    RESULTS.append({"case": case, "equal": equal})
    if not equal:
        RESULTS[-1] |= {"got": repr(got)[:300], "want": repr(want)[:300]}


def image(name, values, colour):
    """A packed 4 x 4 8-bit image of stored values (H, W, 4) in [0, 1]."""
    made = bpy.data.images.new(name, SIDE, SIDE, alpha=True)
    made.colorspace_settings.name = "sRGB" if colour else "Non-Color"
    made.pixels.foreach_set(values.astype(numpy.float32).ravel())
    made.pack()
    return made


def stored(made):
    """The stored values of an image (H, W, 4), rows from v = 0."""
    pixels = numpy.empty(made.size[0] * made.size[1] * 4, numpy.float32)
    made.pixels.foreach_get(pixels)
    return pixels.reshape(made.size[1], made.size[0], 4).astype(numpy.float64)


def material(name):
    """A new material holding only an output; its tree and output node."""
    made = bpy.data.materials.new(name)
    made.use_nodes = True
    tree = made.node_tree
    tree.nodes.clear()
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    return made, tree, output


def texture(tree, made):
    """An Image Texture node of `made`."""
    node = tree.nodes.new("ShaderNodeTexImage")
    node.image = made
    return node


def principled_of(made):
    """The single Principled BSDF of a rewritten material, and whether the tree is
    plain."""
    nodes = list(made.node_tree.nodes)
    shaders = [n for n in nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"]
    plain = len(shaders) == 1 and all(n.bl_idname in PLAIN for n in nodes)
    return shaders[0], plain


def linked_image(socket):
    """The image of the Image Texture feeding a socket (through a Normal Map)."""
    node = socket.links[0].from_node
    if node.bl_idname == "ShaderNodeNormalMap":
        node = node.inputs["Color"].links[0].from_node
    return node.image


def build(rng):
    """The made materials and what each case needs to judge it."""
    made = {}
    m, tree, output = material("fresnel_mix")
    diffuse = tree.nodes.new("ShaderNodeBsdfDiffuse")
    diffuse.inputs["Color"].default_value = (0.6, 0.3, 0.1, 1.0)
    glossy = tree.nodes.new("ShaderNodeBsdfAnisotropic")
    glossy.inputs["Roughness"].default_value = 0.25
    fresnel = tree.nodes.new("ShaderNodeFresnel")
    mix = tree.nodes.new("ShaderNodeMixShader")
    tree.links.new(fresnel.outputs[0], mix.inputs["Fac"])
    tree.links.new(diffuse.outputs[0], mix.inputs[1])
    tree.links.new(glossy.outputs[0], mix.inputs[2])
    tree.links.new(mix.outputs[0], output.inputs["Surface"])
    made["fresnel_mix"] = m
    m, tree, output = material("glossy_alone")
    glossy = tree.nodes.new("ShaderNodeBsdfAnisotropic")
    glossy.inputs["Color"].default_value = (0.9, 0.6, 0.2, 1.0)
    glossy.inputs["Roughness"].default_value = 0.1
    tree.links.new(glossy.outputs[0], output.inputs["Surface"])
    made["glossy_alone"] = m
    m, tree, output = material("transparent_mix")
    cut = rng.integers(0, 256, (SIDE, SIDE, 4)) / 255
    leaf = texture(tree, image("cut", cut, True))
    transparent = tree.nodes.new("ShaderNodeBsdfTransparent")
    diffuse = tree.nodes.new("ShaderNodeBsdfDiffuse")
    mix = tree.nodes.new("ShaderNodeMixShader")
    tree.links.new(leaf.outputs["Alpha"], mix.inputs["Fac"])
    tree.links.new(transparent.outputs[0], mix.inputs[1])
    tree.links.new(diffuse.outputs[0], mix.inputs[2])
    tree.links.new(mix.outputs[0], output.inputs["Surface"])
    made["transparent_mix"] = m
    m, tree, output = material("principled_plain")
    shader = tree.nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Roughness"].default_value = 0.35
    leaf = texture(
        tree, image("plain", rng.integers(0, 256, (SIDE, SIDE, 4)) / 255, True)
    )
    tree.links.new(leaf.outputs["Color"], shader.inputs["Base Color"])
    tree.links.new(shader.outputs[0], output.inputs["Surface"])
    made["principled_plain"] = m
    for name, between in (
        ("invert", "ShaderNodeInvert"),
        ("ramp", "ShaderNodeValToRGB"),
    ):
        m, tree, output = material(name)
        shader = tree.nodes.new("ShaderNodeBsdfPrincipled")
        values = rng.integers(0, 256, (SIDE, SIDE, 4)) / 255
        values[..., 3] = 1
        if name == "ramp":
            values[..., 1] = values[..., 2] = values[..., 0]
        leaf = texture(tree, image(name, values, True))
        node = tree.nodes.new(between)
        if name == "ramp":
            node.color_ramp.elements[1].color = RAMP_END
            tree.links.new(leaf.outputs["Color"], node.inputs["Fac"])
        else:
            tree.links.new(leaf.outputs["Color"], node.inputs["Color"])
        tree.links.new(node.outputs["Color"], shader.inputs["Base Color"])
        tree.links.new(shader.outputs[0], output.inputs["Surface"])
        made[name] = m
    m, tree, output = material("bump")
    shader = tree.nodes.new("ShaderNodeBsdfPrincipled")
    heights = numpy.repeat(rng.integers(0, 256, (SIDE, SIDE, 1)) / 255, 4, axis=2)
    heights[..., 3] = 1
    leaf = texture(tree, image("height", heights, False))
    bump = tree.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = BUMP_STRENGTH
    bump.inputs["Distance"].default_value = BUMP_DISTANCE
    tree.links.new(leaf.outputs["Color"], bump.inputs["Height"])
    tree.links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    tree.links.new(shader.outputs[0], output.inputs["Surface"])
    made["bump"] = m
    m, tree, output = material("noise_object")
    shader = tree.nodes.new("ShaderNodeBsdfPrincipled")
    noise = tree.nodes.new("ShaderNodeTexNoise")
    coordinates = tree.nodes.new("ShaderNodeTexCoord")
    tree.links.new(coordinates.outputs["Object"], noise.inputs["Vector"])
    tree.links.new(noise.outputs["Color"], shader.inputs["Base Color"])
    tree.links.new(shader.outputs[0], output.inputs["Surface"])
    made["noise_object"] = m
    return made


def leaf_values(name):
    """Cycles' linear values of the image `name` at its texels, baked as they are."""
    m, tree, _ = material(f"probe_{name}")
    leaf = texture(tree, bpy.data.images[name])
    values = bake.Baker().bake(m, ((), leaf.name, "Color"), (SIDE, SIDE))
    return values[..., :3].astype(numpy.float64)


def judge(made, record, decoded):
    """Every case against values computed here (`decoded`: Cycles' linear values of
    the leaf images)."""
    for name, m in made.items():
        same(f"{name} plain tree", principled_of(m)[1], True)
    shader = principled_of(made["fresnel_mix"])[0]
    same("fresnel_mix class", record["fresnel_mix"]["class"], "S")
    same("fresnel_mix metallic", shader.inputs["Metallic"].default_value, 0.0)
    same("fresnel_mix roughness", shader.inputs["Roughness"].default_value, 0.25, 1e-6)
    base = list(shader.inputs["Base Color"].default_value)
    same("fresnel_mix base", base, [0.6, 0.3, 0.1, 1.0], 1e-6)
    shader = principled_of(made["glossy_alone"])[0]
    same("glossy_alone metallic", shader.inputs["Metallic"].default_value, 1.0)
    base = list(shader.inputs["Base Color"].default_value)
    same("glossy_alone base", base, [0.9, 0.6, 0.2, 1.0], 1e-6)
    sockets = record["transparent_mix"]["sockets"]
    same("transparent_mix alpha", sockets["Alpha"]["done"], "as_is")
    shader = principled_of(made["transparent_mix"])[0]
    clip = shader.inputs["Alpha"].links[0].from_node
    same(
        "transparent_mix mask",
        (clip.bl_idname, clip.operation),
        ("ShaderNodeMath", "SUBTRACT"),
    )
    same("principled_plain class", record["principled_plain"]["class"], "P")
    sockets = record["principled_plain"]["sockets"]
    done = (sockets["Base Color"]["done"], sockets["Roughness"]["done"])
    same("principled_plain sockets", done, ("as_is", "constant"))
    for name in ("invert", "ramp"):
        same(f"{name} baked", record[name]["sockets"]["Base Color"]["done"], "baked")
        shader = principled_of(made[name])[0]
        got = stored(linked_image(shader.inputs["Base Color"]))[..., :3]
        leaf = decoded[name]
        if name == "invert":
            linear = 1 - leaf
        else:
            linear = leaf[..., :1] * numpy.array(RAMP_END[:3])
        want = bake.encode_srgb(linear)
        same(f"{name} texels", got, want, STEP)
    same("bump done", record["bump"]["sockets"]["Normal"]["done"], "bump")
    shader = principled_of(made["bump"])[0]
    got = stored(linked_image(shader.inputs["Normal"]))[..., :3]
    h = stored(bpy.data.images["height"])[..., 0]
    for y, x in ((0, 0), (1, 2), (3, 3), (2, 1)):
        du = (h[y, (x + 1) % SIDE] - h[y, (x - 1) % SIDE]) * SIDE / 2
        dv = (h[(y + 1) % SIDE, x] - h[(y - 1) % SIDE, x]) * SIDE / 2
        n = numpy.array([-BUMP_DISTANCE * du, -BUMP_DISTANCE * dv, 1.0])
        n /= numpy.linalg.norm(n)
        want = numpy.rint((n * 0.5 + 0.5) * 255) / 255
        same(f"bump texel {x},{y}", got[y, x], want, STEP + 1e-6)
    sockets = record["noise_object"]["sockets"]["Base Color"]
    same(
        "noise_object lost",
        (sockets["done"], sockets.get("node")),
        ("lost", "ShaderNodeTexCoord"),
    )


def main():
    """Builds, rewrites and judges every case."""
    started = time.perf_counter()
    made = build(numpy.random.default_rng(5))
    decoded = {name: leaf_values(name) for name in ("invert", "ramp")}
    record, _, bakes = materials.Rewriter().run(list(made.values()))
    judge(made, {name: record[m.name_full] for name, m in made.items()}, decoded)
    different = [r for r in RESULTS if not r["equal"]]
    common.report(
        {
            "ok": not different,
            "cases": len(RESULTS),
            "different": different,
            "bakes": bakes,
            "seconds": round(time.perf_counter() - started, 1),
        }
    )


main()
