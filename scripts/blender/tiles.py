"""Helpers the export imports inside Blender: a rebuilt material whose images hold UDIM
tiles split by tile: each of its triangles goes to the tile its uv centroid lies in, its
corners moved onto that tile, and a copy of the material a tile reads that tile's file.
"""

import bmesh
import bpy
import numpy
from meshbake import faces_of, loop_uv

MISSING = (1.0, 0.0, 1.0, 1.0)  # Cycles' colour of a tile an image lacks


def tiled_specs(choices):
    """The image specs of a material's choices whose image holds UDIM tiles."""
    return [
        c["spec"]
        for c in choices.values()
        if "spec" in c and c["spec"]["image"].source == "TILED"
    ]


def one_space(choices):
    """True when every tiled image of the choices reads one uv map without a Mapping."""
    coords = {spec["coord"] for spec in tiled_specs(choices)}
    return len(coords) <= 1 and all(c[1] is None for c in coords)


def triangulate(mesh, material):
    """The faces of `mesh` carrying `material` split into triangles."""
    work = bmesh.new()
    work.from_mesh(mesh)
    work.faces.ensure_lookup_table()
    chosen = set(faces_of(mesh, material).tolist())
    faces = [f for f in work.faces if f.index in chosen and len(f.verts) > 3]
    if faces:
        bmesh.ops.triangulate(work, faces=faces)
        work.to_mesh(mesh)
    work.free()


def tile_file(image, number):
    """The path of one tile's file of a tiled image."""
    path = bpy.path.abspath(image.filepath_raw, library=image.library)
    u, v = (number - 1001) % 10, (number - 1001) // 10
    path = path.replace("<UDIM>", str(number))
    return path.replace("<UVTILE>", f"u{u + 1}_v{v + 1}")


def tile_image(image, number, cache):
    """One tile of a tiled image as an image of its own (loaded once)."""
    key = (image.name_full, number)
    if key not in cache:
        made = bpy.data.images.load(tile_file(image, number), check_existing=True)
        made.colorspace_settings.name = image.colorspace_settings.name
        made.alpha_mode = image.alpha_mode
        cache[key] = made
    return cache[key]


def tile_material(material, number, cache):
    """A copy of a rebuilt material whose tiled images read tile `number` (clamped at
    its edges); where an image lacks the tile, its outputs give Cycles' missing value.
    """
    key = (material.name_full, number)
    if key in cache:
        return cache[key]
    copy = material.copy()
    copy.name = f"{material.name}.{number}"
    tree = copy.node_tree
    for node in list(tree.nodes):
        image = getattr(node, "image", None)
        if node.bl_idname != "ShaderNodeTexImage" or image is None:
            continue
        if image.source != "TILED":
            continue
        if number in [t.number for t in image.tiles]:
            node.image = tile_image(image, number, cache)
            node.extension = "EXTEND"
            continue
        for out in node.outputs:
            for link in list(out.links):
                socket = link.to_socket
                tree.links.remove(link)
                if hasattr(socket.default_value, "__len__"):
                    socket.default_value = MISSING[: len(socket.default_value)]
                else:
                    socket.default_value = 1.0
        tree.nodes.remove(node)
    cache[key] = copy
    return copy


def split(material, choices, meshes, cache):
    """Each mesh's faces of a rebuilt material moved to their tiles' copies of it;
    {"tiles": numbers used, "missing": triangles in a tile some image lacks}."""
    specs = tiled_specs(choices)
    uv_name = specs[0]["coord"][0]
    present = set.intersection(*({t.number for t in s["image"].tiles} for s in specs))
    used, missing = set(), 0
    for mesh in meshes:
        triangulate(mesh, material)
        faces = faces_of(mesh, material)
        uv = loop_uv(mesh, uv_name)
        if not len(faces) or uv is None:
            continue
        start = numpy.empty(len(mesh.polygons), numpy.int32)
        mesh.polygons.foreach_get("loop_start", start)
        corners = start[faces][:, None] + numpy.arange(3)
        whole = numpy.floor(uv[corners].mean(axis=1))
        number = 1001 + whole[:, 0] + 10 * whole[:, 1]
        number = numpy.where(
            (whole[:, 0] >= 0) & (whole[:, 0] < 10) & (whole[:, 1] >= 0), number, 0
        ).astype(numpy.int64)
        uv[corners] -= whole[:, None, :]
        layer = mesh.uv_layers.get(uv_name) if uv_name else None
        layer = layer or next(u for u in mesh.uv_layers if u.active_render)
        layer.uv.foreach_set("vector", uv.astype(numpy.float32).ravel())
        index = numpy.empty(len(mesh.polygons), numpy.int32)
        mesh.polygons.foreach_get("material_index", index)
        for tile in numpy.unique(number):
            copy = tile_material(material, int(tile), cache)
            if copy.name_full not in [m.name_full for m in mesh.materials if m]:
                mesh.materials.append(copy)
            slot = [m.name_full if m else "" for m in mesh.materials].index(
                copy.name_full
            )
            index[faces[number == tile]] = slot
            used.add(int(tile))
            missing += int(tile not in present) * int(numpy.sum(number == tile))
        mesh.polygons.foreach_set("material_index", index)
    return {"tiles": sorted(used), "missing": missing}
