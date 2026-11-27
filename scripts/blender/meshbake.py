"""Helpers the export imports inside Blender: the atlas of a material over all the meshes
that carry it (their faces at each mesh's first copy, joined and unwrapped by Smart UV
Project into one shared layout), written back into each mesh's first uv layer, its
passes handed to the bake jobs."""

import math

import bake
import bakejobs
import bmesh
import bpy
import numpy
from graph import chain, resolve

BAKE_UV = "prism_bake"
LOOP = "prism_loop"
OWNER = "prism_owner"
ANGLE = math.radians(66.0)  # Smart UV Project's angle limit
GAP_TEXELS = 2  # the islands' margin in texels of the bake
CONSTANT_ONLY = {"Emission Strength", "IOR"}
TEXELS_A_FEATURE = 8  # texels a unit of a procedural texture's Scale
FACE_TEXELS = 16  # texels a median face for vertex or object data
SMALL_SHARE = 0.1  # surface share under a texel past which the side doubles
LOST_SHARE = 0.5  # surface share under a texel at the cap past which the atlas is lost


def faces_of(mesh, material):
    """The indices of a mesh's faces whose slot holds `material`."""
    slots = [i for i, m in enumerate(mesh.materials) if m == material]
    index = numpy.empty(len(mesh.polygons), numpy.int32)
    mesh.polygons.foreach_get("material_index", index)
    return numpy.nonzero(numpy.isin(index, slots))[0]


def loop_uv(mesh, name):
    """(L, 2) uv of a mesh's corners in the layer `name` ("" the active render one)."""
    layer = mesh.uv_layers.get(name) if name else None
    layer = layer or next((u for u in mesh.uv_layers if u.active_render), None)
    if layer is None:
        return None
    uv = numpy.empty(len(mesh.loops) * 2, numpy.float32)
    layer.uv.foreach_get("vector", uv)
    return uv.reshape(-1, 2).astype(numpy.float64)


def uv_area(mesh, name):
    """The area the faces of a mesh cover in the uv layer `name`."""
    return float(face_uv_areas(mesh, name).sum())


def face_uv_areas(mesh, name):
    """The area each face of a mesh covers in the uv layer `name` (0 without one)."""
    uv = loop_uv(mesh, name)
    if uv is None:
        return numpy.zeros(len(mesh.polygons))
    start = numpy.empty(len(mesh.polygons), numpy.int32)
    mesh.polygons.foreach_get("loop_start", start)
    total = numpy.empty(len(mesh.polygons), numpy.int32)
    mesh.polygons.foreach_get("loop_total", total)
    owner = numpy.repeat(numpy.arange(len(start)), total)
    following = numpy.arange(len(uv)) + 1
    last = (start + total - 1)[owner]
    following = numpy.where(numpy.arange(len(uv)) == last, start[owner], following)
    cross = uv[:, 0] * uv[following, 1] - uv[following, 0] * uv[:, 1]
    return numpy.abs(numpy.bincount(owner, cross, len(start))) / 2


def mapping_scale(path, socket, space):
    """The largest scale of the Mapping in front of an image (1 without one)."""
    if space[0] != "geometry" and space[1] is not None:
        return max(abs(v) for v in space[1][3])
    found = resolve(path, socket)
    if found[0] == "out" and found[2].node.bl_idname == "ShaderNodeMapping":
        scale = resolve(found[1], found[2].node.inputs["Scale"])
        if scale[0] == "const":
            return max(abs(v) for v in scale[1])
    return 1.0


def face_areas(mesh):
    """The world area of each face of a holder's mesh."""
    area = numpy.empty(len(mesh.polygons), numpy.float64)
    mesh.polygons.foreach_get("area", area)
    return area


def leaf_texels(node, at, space, mesh, area):
    """Texels a unit of length one image or procedural leaf asks on `mesh` (0 when its
    scale is not a constant)."""
    if node.bl_idname == "ShaderNodeTexImage":
        if node.image is None:
            return 0.0
        across = float(max(node.image.size[0], node.image.size[1]))
    else:
        scale = node.inputs.get("Scale")
        found = resolve(at, scale) if scale is not None else ("out",)
        if found[0] != "const":
            return 0.0
        across = abs(float(found[1])) * TEXELS_A_FEATURE
    vector = node.inputs.get("Vector")
    if vector is not None:
        across *= mapping_scale(at, vector, space)
    if space[0] != "geometry":
        across *= math.sqrt(uv_area(mesh, space[0]) / area)
    return across


def density(feeds, mesh):
    """Texels a unit of surface the feeds' chains ask on a holder's mesh: the densest
    image or procedural, or FACE_TEXELS a median face for vertex or object data."""
    faces = face_areas(mesh)
    area = float(faces.sum())
    if area <= 0:
        return 0.0
    best, data = 0.0, False
    for path, out in feeds:
        info = chain(path, out)
        data |= bool(info["data"])
        for node, at, space in info["leaves"]:
            best = max(best, leaf_texels(node, at, space, mesh, area) ** 2)
    if data or best == 0.0:
        best = max(best, FACE_TEXELS / max(float(numpy.median(faces)), 1e-30))
    return best


def surface_side(feeds, holders):
    """(wanted, given) atlas side: the holders' surface times the texels a unit of it,
    as one square side rounded up to a power of two; given at most MOST_SIDE."""
    texels = sum(face_areas(h.data).sum() * density(feeds, h.data) for h in holders)
    wanted = 2 ** math.ceil(math.log2(max(math.sqrt(max(texels, 1.0)), 1.0)))
    wanted = max(int(wanted), bake.NO_IMAGE_SIDE)
    return wanted, min(wanted, bake.MOST_SIDE)


def isolate(baker, mesh, material, matrix, owner):
    """An object of the bake scene holding a copy of the faces of `mesh` that carry
    `material` (each corner keeping its index in LOOP and `owner` in OWNER), moved by
    `matrix`."""
    copy = mesh.copy()
    copy.name = f"prism_bake_{mesh.name}"
    corners = copy.attributes.new(LOOP, "INT", "CORNER")
    corners.data.foreach_set("value", numpy.arange(len(copy.loops), dtype=numpy.int32))
    owners = copy.attributes.new(OWNER, "INT", "CORNER")
    owners.data.foreach_set("value", numpy.full(len(copy.loops), owner, numpy.int32))
    keep = numpy.zeros(len(copy.polygons), bool)
    keep[faces_of(mesh, material)] = True
    work = bmesh.new()
    work.from_mesh(copy)
    work.faces.ensure_lookup_table()
    gone = [f for f in work.faces if not keep[f.index]]
    bmesh.ops.delete(work, geom=gone, context="FACES")
    work.to_mesh(copy)
    work.free()
    copy.polygons.foreach_set("material_index", [0] * len(copy.polygons))
    copy.transform(matrix)
    if matrix.determinant() < 0:
        copy.flip_normals()
    holder = bpy.data.objects.new(copy.name, copy)
    baker.scene.collection.objects.link(holder)
    return holder


def in_bake_scene(baker, holders, operator, **arguments):
    """Runs `operator` in the bake scene with `holders` selected, the first active."""
    window = bpy.context.window
    previous = window.scene
    window.scene = baker.scene
    layer = baker.scene.view_layers[0]
    try:
        for obj in layer.objects:
            obj.select_set(obj in holders)
        layer.objects.active = holders[0]
        with bpy.context.temp_override(
            window=window,
            scene=baker.scene,
            view_layer=layer,
            active_object=holders[0],
            selected_objects=holders,
            selected_editable_objects=holders,
        ):
            operator(**arguments)
    finally:
        window.scene = previous


def join(baker, holders):
    """The holders joined into the first of them (one object, one Cycles bake)."""
    if len(holders) == 1:
        return holders[0]
    meshes = [h.data for h in holders[1:]]
    in_bake_scene(baker, holders, bpy.ops.object.join)
    for mesh in meshes:
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    return holders[0]


def project(baker, holders, side):
    """A uv layer BAKE_UV on every holder by one Smart UV Project over all of them
    (their islands packed together, GAP_TEXELS apart at `side`)."""
    for holder in holders:
        mesh = holder.data
        layer = mesh.uv_layers.get(BAKE_UV) or mesh.uv_layers.new(name=BAKE_UV)
        mesh.uv_layers.active = layer
        mesh.polygons.foreach_set("select", [True] * len(mesh.polygons))
    window = bpy.context.window
    previous = window.scene
    window.scene = baker.scene
    layer = baker.scene.view_layers[0]
    try:
        for obj in layer.objects:
            obj.select_set(obj in holders)
        layer.objects.active = holders[0]
        with bpy.context.temp_override(
            window=window, scene=baker.scene, view_layer=layer
        ):
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.uv.smart_project(
                angle_limit=ANGLE,
                island_margin=GAP_TEXELS / side,
                margin_method="FRACTION",
                area_weight=0.0,
                correct_aspect=True,
                scale_to_bounds=False,
            )
            bpy.ops.object.mode_set(mode="OBJECT")
    finally:
        window.scene = previous


def under_a_texel(holders, side):
    """The share of the holders' surface on faces covering less than one texel of the
    atlas in BAKE_UV."""
    small = total = 0.0
    for holder in holders:
        area = face_areas(holder.data)
        under = face_uv_areas(holder.data, BAKE_UV) * side * side < 1.0
        small, total = small + area[under].sum(), total + area.sum()
    return round(float(small / max(total, 1e-30)), 4)


def write_back(mesh, holder, owner):
    """The joined holder's BAKE_UV at the corners of `owner` written into the mesh's
    first uv layer at the corners they came from (made when the mesh has none); that
    layer made the render one."""
    if not len(mesh.uv_layers):
        mesh.uv_layers.new(name=bake.DEFAULT_UV)
    target = mesh.uv_layers[0]
    uv = numpy.empty(len(mesh.loops) * 2, numpy.float32)
    target.uv.foreach_get("vector", uv)
    uv = uv.reshape(-1, 2)
    source = holder.data
    baked = numpy.empty(len(source.loops) * 2, numpy.float32)
    source.uv_layers[BAKE_UV].uv.foreach_get("vector", baked)
    origin = numpy.empty(len(source.loops), numpy.int32)
    source.attributes[LOOP].data.foreach_get("value", origin)
    owners = numpy.empty(len(source.loops), numpy.int32)
    source.attributes[OWNER].data.foreach_get("value", owners)
    mine = owners == owner
    uv[origin[mine]] = baked.reshape(-1, 2)[mine]
    mesh.uv_layers[0].uv.foreach_set("vector", uv.ravel())
    mesh.uv_layers[0].active_render = True
    mesh.uv_layers.active_index = 0


def lost_choice(choice, cause):
    """A carried socket given up: lost with `cause` and its mean when it has one."""
    found = {"done": "lost", "node": cause}
    return found | ({"value": choice["value"]} if "value" in choice else {})


def carried(name, choice):
    """True when a socket's choice is baked on the mesh in a mesh-baked material."""
    if name in CONSTANT_ONLY or "feed" not in choice:
        return False
    return choice["done"] in ("as_is", "baked", "bump", "mesh_baked")


def per_object(choice):
    """True when a carried socket's chain reads a value that differs by object."""
    return chain(*choice["feed"])["per_object"]


def prepare_atlas(baker, jobs, material, choices, meshes):
    """The atlas of `material` over `meshes` ((mesh, first matrix, objects) each):
    unwrapped, its side chosen, the uvs written back and each pass of its carried
    sockets handed to `jobs`; the state `finish_atlas` takes."""
    feeds = [c["feed"] for n, c in choices.items() if carried(n, c)]
    holders = [
        isolate(baker, mesh, material, matrix, i)
        for i, (mesh, matrix, _) in enumerate(meshes)
    ]
    try:
        wanted, side = surface_side(feeds, holders)
        holders = [join(baker, holders)]
        project(baker, holders, side)
        small = under_a_texel(holders, side)
        while small > SMALL_SHARE and side < bake.MOST_SIDE:
            side *= 2
            project(baker, holders, side)
            small = under_a_texel(holders, side)
        if small > SMALL_SHARE:
            wanted = max(wanted, 2 * side)
        record = {"side": side, "meshes": len(meshes), "under_a_texel": small}
        record |= {"cut": [wanted, side]} if wanted > side else {}
        state = {"choices": choices, "record": record, "keys": [], "per_object": set()}
        if small > LOST_SHARE:
            return state
        for i, (mesh, _, _) in enumerate(meshes):
            write_back(mesh, holders[0], i)
        names = [n for n, c in choices.items() if carried(n, c)]
        shared = any(count > 1 for _, _, count in meshes)
        state["per_object"] = {n for n in names if shared and per_object(choices[n])}
        atlas = (material.name, side)
        for kind, group in bakejobs.passes(names):
            sockets = []
            for name in group:
                path, out = choices[name]["feed"]
                target = (tuple(n.name for n in path), out.node.name, out.identifier)
                sockets.append((name, target, choices[name].get("one_minus", False)))
            key = jobs.add(
                baker, material, atlas, holders[0], BAKE_UV, side, kind, sockets
            )
            state["keys"].append(key)
        jobs.close(atlas)
        return state
    finally:
        for holder in holders:
            data = holder.data
            bpy.data.objects.remove(holder)
            bpy.data.meshes.remove(data)


def finish_atlas(jobs, material, state):
    """The choices of an atlas from its passes' results: (choices, record)."""
    choices, record = state["choices"], state["record"]
    if record["under_a_texel"] > LOST_SHARE:
        lost = {
            n: lost_choice(c, "bake under a texel") if carried(n, c) else c
            for n, c in choices.items()
        }
        return lost, record
    own = {n: c for n, c in choices.items() if not carried(n, c)}
    for key in state["keys"]:
        found = jobs.result(key, material)
        for name in found or {}:
            own[name] = found[name]
    for name, choice in choices.items():
        if name not in own:
            own[name] = lost_choice(choice, "bake job failed")
        elif name in state["per_object"]:
            own[name]["per_object"] = "first object's"
    for name, choice in own.items():
        if (
            choice["done"] == "lost"
            and "value" not in choice
            and "value" in choices[name]
        ):
            choice["value"] = choices[name]["value"]
    return own, record
