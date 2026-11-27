"""Run inside Blender on an empty file: the material rewrite on made materials against
values computed here; one JSON line with `ok`.
`blender --background --factory-startup --python selftest_materials.py`"""

import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bake
import bpy
import common
import materials
import numpy
import tiles
from mathutils import Matrix

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
PLANE_SIDE, COPY_SCALE, MAPPING_SCALE = 4.0, 0.5, 4.0
SHEEN = (0.4, (0.8, 0.6, 0.4, 1.0), 0.3)
SHEEN_SOCKETS = ("Sheen Weight", "Sheen Tint", "Sheen Roughness")
MIX_FACTOR = 0.25
MESH_FACES = 8  # 2 planes of 8 x 8 faces at 16 texels a face give a 64-texel atlas
ATLAS_SIDE = 64
POSITION_SCALE, POSITION_OFFSET = 0.5, 0.25
ROUGH = (0.2, 0.6)
COLOURS = ((0.8, 0.2, 0.1, 1.0), (0.2, 0.4, 0.9, 1.0))
GLASS_COLOUR = (0.9, 0.95, 1.0, 1.0)
TILE_COLOURS = {1001: (255, 0, 0), 1002: (0, 0, 255)}
# Triangles of the UDIM case: uv corners, and the tile its centroid lies in.
TILED_TRIANGLES = (
    (((0.1, 0.1), (0.9, 0.1), (0.5, 0.9)), 1001),
    (((1.1, 0.1), (1.9, 0.1), (1.5, 0.9)), 1002),
    (((0.9, 0.2), (1.8, 0.2), (1.8, 0.8)), 1002),
    (((2.1, 0.1), (2.9, 0.1), (2.5, 0.9)), 1003),
)
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


def connect(tree, output, shader):
    """Links a shader into a material's output."""
    tree.links.new(shader.outputs[0], output.inputs["Surface"])


def build_rows(made):
    """The materials of the shader table's later rows: two Principled BSDFs mixed, a
    factor constant for camera rays, a Glass under a Glossy, an unlinked shader input.
    """
    m, tree, output = material("principled_mix")
    sides = [tree.nodes.new("ShaderNodeBsdfPrincipled") for _ in range(2)]
    for shader, colour, rough in zip(sides, COLOURS, ROUGH, strict=True):
        shader.inputs["Base Color"].default_value = colour
        shader.inputs["Roughness"].default_value = rough
    mix = tree.nodes.new("ShaderNodeMixShader")
    mix.inputs["Fac"].default_value = MIX_FACTOR
    tree.links.new(sides[0].outputs[0], mix.inputs[1])
    tree.links.new(sides[1].outputs[0], mix.inputs[2])
    connect(tree, output, mix)
    made["principled_mix"] = m
    m, tree, output = material("sheen")
    shader = tree.nodes.new("ShaderNodeBsdfPrincipled")
    for name, value in zip(SHEEN_SOCKETS, SHEEN, strict=True):
        shader.inputs[name].default_value = value
    connect(tree, output, shader)
    made["sheen"] = m
    m, tree, output = material("camera_factor")
    path = tree.nodes.new("ShaderNodeLightPath")
    add = tree.nodes.new("ShaderNodeMath")
    tree.links.new(path.outputs["Is Shadow Ray"], add.inputs[0])
    tree.links.new(path.outputs["Is Diffuse Ray"], add.inputs[1])
    glass = tree.nodes.new("ShaderNodeBsdfGlass")
    glass.inputs["Color"].default_value = GLASS_COLOUR
    clear = tree.nodes.new("ShaderNodeBsdfTransparent")
    mix = tree.nodes.new("ShaderNodeMixShader")
    tree.links.new(add.outputs[0], mix.inputs["Fac"])
    tree.links.new(glass.outputs[0], mix.inputs[1])
    tree.links.new(clear.outputs[0], mix.inputs[2])
    connect(tree, output, mix)
    made["camera_factor"] = m
    m, tree, output = material("glass_glossy")
    glass = tree.nodes.new("ShaderNodeBsdfGlass")
    glass.inputs["Color"].default_value = GLASS_COLOUR
    glass.inputs["Roughness"].default_value = ROUGH[0]
    glossy = tree.nodes.new("ShaderNodeBsdfAnisotropic")
    facing = tree.nodes.new("ShaderNodeLayerWeight")
    mix = tree.nodes.new("ShaderNodeMixShader")
    tree.links.new(facing.outputs["Facing"], mix.inputs["Fac"])
    tree.links.new(glass.outputs[0], mix.inputs[1])
    tree.links.new(glossy.outputs[0], mix.inputs[2])
    connect(tree, output, mix)
    made["glass_glossy"] = m
    m, tree, output = material("one_linked")
    diffuse = tree.nodes.new("ShaderNodeBsdfDiffuse")
    diffuse.inputs["Color"].default_value = COLOURS[0]
    mix = tree.nodes.new("ShaderNodeMixShader")
    mix.inputs["Fac"].default_value = 0.15
    tree.links.new(diffuse.outputs[0], mix.inputs[1])
    connect(tree, output, mix)
    made["one_linked"] = m


def plane(name, x0, faces, uv=None):
    """A unit square of faces x faces quads (or triangles with uv) in the plane z = 0
    starting at x0."""
    mesh = bpy.data.meshes.new(name)
    if uv is None:
        n = faces + 1
        points = [(x0 + i / faces, j / faces, 0.0) for j in range(n) for i in range(n)]
        polygons = [
            (j * n + i, j * n + i + 1, (j + 1) * n + i + 1, (j + 1) * n + i)
            for j in range(faces)
            for i in range(faces)
        ]
        mesh.from_pydata(points, [], polygons)
        mesh.uv_layers.new(name="UVMap")
        return mesh
    points = [(x0 + u, v, 0.0) for corners, _ in uv for u, v in corners]
    mesh.from_pydata(
        points, [], [(3 * i, 3 * i + 1, 3 * i + 2) for i in range(len(uv))]
    )
    layer = mesh.uv_layers.new(name="UVMap")
    layer.uv.foreach_set("vector", [c for corners, _ in uv for p in corners for c in p])
    return mesh


def tiled_image(folder):
    """A tiled image of two 4 x 4 tiles (1001 red, 1002 blue) saved as files."""
    for number, colour in TILE_COLOURS.items():
        made = bpy.data.images.new(f"tile_{number}", SIDE, SIDE)
        values = numpy.ones((SIDE, SIDE, 4), numpy.float32)
        values[..., :3] = numpy.array(colour) / 255
        made.pixels.foreach_set(values.ravel())
        made.filepath_raw = os.path.join(folder, f"tiled.{number}.png")
        made.file_format = "PNG"
        made.save()
    tiled = bpy.data.images.load(os.path.join(folder, "tiled.1001.png"))
    tiled.source = "TILED"
    tiled.filepath_raw = os.path.join(folder, "tiled.<UDIM>.png")
    tiled.reload()
    return tiled


def build_meshes(made, folder):
    """The materials of the mesh bake and the UDIM split on meshes of their own, and
    the geometry keys holding those meshes."""
    m, tree, output = material("position")
    shader = tree.nodes.new("ShaderNodeBsdfPrincipled")
    geometry = tree.nodes.new("ShaderNodeNewGeometry")
    split = tree.nodes.new("ShaderNodeSeparateXYZ")
    tree.links.new(geometry.outputs["Position"], split.inputs[0])
    scaled = tree.nodes.new("ShaderNodeMath")
    scaled.operation = "MULTIPLY_ADD"
    scaled.inputs[1].default_value = POSITION_SCALE
    scaled.inputs[2].default_value = POSITION_OFFSET
    tree.links.new(split.outputs["X"], scaled.inputs[0])
    tree.links.new(scaled.outputs[0], shader.inputs["Base Color"])
    connect(tree, output, shader)
    made["position"] = m
    m, tree, output = material("random")
    shader = tree.nodes.new("ShaderNodeBsdfPrincipled")
    info = tree.nodes.new("ShaderNodeObjectInfo")
    tree.links.new(info.outputs["Random"], shader.inputs["Base Color"])
    connect(tree, output, shader)
    made["random"] = m
    m, tree, output = material("udim")
    shader = tree.nodes.new("ShaderNodeBsdfPrincipled")
    leaf = texture(tree, tiled_image(folder))
    tree.links.new(leaf.outputs["Color"], shader.inputs["Base Color"])
    connect(tree, output, shader)
    made["udim"] = m
    m, tree, output = material("bump_metres")
    shader = tree.nodes.new("ShaderNodeBsdfPrincipled")
    leaf = texture(tree, bpy.data.images["height"])
    coordinates = tree.nodes.new("ShaderNodeTexCoord")
    moved = tree.nodes.new("ShaderNodeMapping")
    moved.inputs["Scale"].default_value = (MAPPING_SCALE, MAPPING_SCALE, 1.0)
    tree.links.new(coordinates.outputs["UV"], moved.inputs["Vector"])
    tree.links.new(moved.outputs["Vector"], leaf.inputs["Vector"])
    bump = tree.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = BUMP_STRENGTH
    bump.inputs["Distance"].default_value = BUMP_DISTANCE
    tree.links.new(leaf.outputs["Color"], bump.inputs["Height"])
    tree.links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    connect(tree, output, shader)
    made["bump_metres"] = m
    side = [((0, 0), (1, 0), (1, 1)), ((0, 0), (1, 1), (0, 1))]
    square = plane("bump_metres", 0.0, 0, [(corners, None) for corners in side])
    for vertex in square.vertices:
        vertex.co *= PLANE_SIDE
    square.materials.append(m)
    meshes = {
        "bump_metres": square,
        "position_a": plane("position_a", 0.0, MESH_FACES),
        "position_b": plane("position_b", 0.0, MESH_FACES),
        "udim": plane("udim", 0.0, 0, TILED_TRIANGLES),
        "random": plane("random", 0.0, 2),
    }
    meshes["position_a"].materials.append(made["position"])
    meshes["position_b"].materials.append(made["position"])
    meshes["udim"].materials.append(made["udim"])
    meshes["random"].materials.append(made["random"])
    lifted = Matrix.Translation((0.0, 2.0, 0.0))
    shrunk = Matrix.Diagonal((COPY_SCALE, COPY_SCALE, COPY_SCALE, 1.0))
    matrices = {"position_b": [lifted], "random": [Matrix.Identity(4), lifted]}
    matrices["bump_metres"] = [shrunk]
    return {
        ("data", name, 0): {
            "source": mesh,
            "triangles": len(mesh.polygons),
            "matrices": matrices.get(name, [Matrix.Identity(4)]),
        }
        for name, mesh in meshes.items()
    }


def judge_rows(made, record):
    """The later rows of the shader table against the inputs computed here."""
    shader = principled_of(made["principled_mix"])[0]
    same("principled_mix class", record["principled_mix"]["class"], "S")
    want = (1 - MIX_FACTOR) * ROUGH[0] + MIX_FACTOR * ROUGH[1]
    same(
        "principled_mix roughness", shader.inputs["Roughness"].default_value, want, 1e-4
    )
    want = (1 - MIX_FACTOR) * numpy.array(COLOURS[0]) + MIX_FACTOR * numpy.array(
        COLOURS[1]
    )
    got = list(shader.inputs["Base Color"].default_value)
    same("principled_mix base", got, want, 1e-4)
    for name in ("camera_factor", "glass_glossy"):
        shader = principled_of(made[name])[0]
        same(f"{name} class", record[name]["class"], "S")
        same(f"{name} glass", shader.inputs["Transmission Weight"].default_value, 1.0)
        base = list(shader.inputs["Base Color"].default_value)
        same(f"{name} base", base, GLASS_COLOUR, 1e-6)
    shader = principled_of(made["glass_glossy"])[0]
    got = shader.inputs["Roughness"].default_value
    same("glass_glossy roughness", got, ROUGH[0], 1e-6)
    shader = principled_of(made["one_linked"])[0]
    same("one_linked class", record["one_linked"]["class"], "S")
    base = list(shader.inputs["Base Color"].default_value)
    same("one_linked base", base, COLOURS[0], 1e-6)


def judge_meshes(found, record):
    """The mesh bake (one atlas over both meshes, the base colour = a x + b at each
    face's centre, no unwritten texel), a per-object value's record, and the UDIM split
    (each triangle on its centroid's tile)."""
    meshes = {key[1]: v["source"] for key, v in found.items()}
    entry = record["position"]
    same("position meshes", sorted(entry["meshes"]), ["position_a", "position_b"])
    same("position done", entry["sockets"]["Base Color"]["done"], "mesh_baked")
    atlas = entry["atlas"]
    same("position atlas", (atlas["side"], atlas["meshes"]), (ATLAS_SIDE, 2))
    low, high = POSITION_OFFSET, POSITION_OFFSET + POSITION_SCALE
    texels = set()
    for name in ("position_a", "position_b"):
        mesh = meshes[name]
        rebuilt = mesh.materials[0]
        same(f"{name} material", rebuilt.name, "position")
        shader, plain = principled_of(rebuilt)
        same(f"{name} plain tree", plain, True)
        values = stored(linked_image(shader.inputs["Base Color"]))[..., :3]
        rows, columns = values.shape[:2]
        same(f"{name} side", (rows, columns), (ATLAS_SIDE, ATLAS_SIDE))
        linear = bake.decode_srgb(values).mean(axis=-1)
        span = (float(linear.min()), float(linear.max()))
        same(f"{name} every texel written", span, (low, high), 2.5 / 255 + 0.01)
        uv = meshbake_uv(mesh)
        for face in mesh.polygons:
            corners = list(face.loop_indices)
            u, v = uv[corners].mean(axis=0)
            texels.add((int(v * rows), int(u * columns)))
            x = numpy.mean([mesh.vertices[i].co.x for i in face.vertices])
            want = POSITION_SCALE * x + POSITION_OFFSET
            across = numpy.ptp(uv[corners], axis=0).max() * rows
            tolerance = POSITION_SCALE / MESH_FACES / max(across, 1.0) + 2.5 / 255
            got = float(linear[int(v * rows), int(u * columns)])
            same(f"{name} face {face.index} x", got, want, tolerance)
    same("position faces apart", len(texels), 2 * MESH_FACES * MESH_FACES)
    entry = record["random"]["sockets"]["Base Color"]
    same("random per object", entry.get("per_object"), "first object's")
    mesh = meshes["udim"]
    entry = record["udim"]
    same("udim tiles", entry["tiles"], [1001, 1002, 1003])
    same("udim missing", entry["missing"], 1)
    uv = meshbake_uv(mesh)
    for face, (_, tile) in zip(mesh.polygons, TILED_TRIANGLES, strict=True):
        assigned = mesh.materials[face.material_index]
        same(f"udim face {face.index} tile", assigned.name, f"udim.{tile}")
        centre = uv[list(face.loop_indices)].mean(axis=0)
        same(
            f"udim face {face.index} on its tile",
            bool(numpy.all(centre // 1 == 0)),
            True,
        )
        shader = principled_of(assigned)[0]
        socket = shader.inputs["Base Color"]
        if tile in TILE_COLOURS:
            image = linked_image(socket)
            same(
                f"udim {tile} file",
                (image.source, os.path.basename(image.filepath)),
                ("FILE", f"tiled.{tile}.png"),
            )
        else:
            same("udim missing tile", list(socket.default_value), list(tiles.MISSING))


def meshbake_uv(mesh):
    """(L, 2) uv of a mesh's first layer."""
    uv = numpy.empty(len(mesh.loops) * 2, numpy.float32)
    mesh.uv_layers[0].uv.foreach_get("vector", uv)
    return uv.reshape(-1, 2).astype(numpy.float64)


def bump_texels(case, got, h, scale):
    """The normal map at four texels against the formula, slopes times `scale`."""
    for y, x in ((0, 0), (1, 2), (3, 3), (2, 1)):
        du = (h[y, (x + 1) % SIDE] - h[y, (x - 1) % SIDE]) * SIDE / 2 * scale
        dv = (h[(y + 1) % SIDE, x] - h[(y - 1) % SIDE, x]) * SIDE / 2 * scale
        n = numpy.array([-BUMP_DISTANCE * du, -BUMP_DISTANCE * dv, 1.0])
        n /= numpy.linalg.norm(n)
        want = numpy.rint((n * 0.5 + 0.5) * 255) / 255
        same(f"{case} texel {x},{y}", got[y, x], want, STEP + 1e-6)


def judge_metres_sheen(made, record):
    """The bump's slope a metre (a 4 m square drawn at half size, a Mapping of scale 4)
    and the sheen inputs kept."""
    sockets = record["bump_metres"]["sockets"]["Normal"]
    same("bump_metres done", sockets["done"], "bump")
    metres = PLANE_SIDE * COPY_SCALE
    same("bump_metres length", sockets["length"]["metres"], metres, 0.01)
    shader = principled_of(made["bump_metres"])[0]
    got = stored(linked_image(shader.inputs["Normal"]))[..., :3]
    h = stored(bpy.data.images["height"])[..., 0]
    bump_texels("bump_metres", got, h, MAPPING_SCALE / metres)
    shader = principled_of(made["sheen"])[0]
    folded = (1.0, [SHEEN[0] * c for c in SHEEN[1][:3]] + [1.0], SHEEN[2])
    for name, value in zip(SHEEN_SOCKETS, folded, strict=True):
        got = shader.inputs[name].default_value
        got = list(got) if hasattr(got, "__len__") else got
        same(f"sheen {name}", got, value, 1e-6)


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
        if name not in ("position", "udim"):
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
    bump_texels("bump", got, h, 1.0)
    sockets = record["noise_object"]["sockets"]["Base Color"]
    same(
        "noise_object lost",
        (sockets["done"], sockets.get("node")),
        ("lost", "ShaderNodeTexCoord"),
    )


def main():
    """Builds, rewrites and judges every case."""
    started = time.perf_counter()
    folder = tempfile.mkdtemp(prefix="selftest_", dir=os.environ.get("PRISM_CACHE"))
    try:
        made = build(numpy.random.default_rng(5))
        build_rows(made)
        found = build_meshes(made, folder)
        decoded = {name: leaf_values(name) for name in ("invert", "ramp")}
        rewriter = materials.Rewriter(os.path.join(folder, "bakes"))
        record, _, bakes = rewriter.run(list(made.values()), found)
        by_case = {name: record[m.name_full] for name, m in made.items()}
        judge(made, by_case, decoded)
        judge_rows(made, by_case)
        judge_meshes(found, by_case)
        judge_metres_sheen(made, by_case)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
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
