"""The surface of a scene of the description per pixel: the rasterizer's triangle, then
the position, normals, filtered base colour, metallic, roughness, occlusion and emission
computed from the pixel's ray and the triangle's plane."""

import numpy as np

from prism_reference.material.filter import COLOUR, DATA, FILTERS, Texture
from prism_reference.material.tangents import tangents, unit_rows
from prism_reference.raster.frames import rasterize
from prism_reference.scene.artist.convert import transformed
from prism_reference.scene.artist.materials import transmission_factor
from prism_reference.scene.description.flatten import draws, flatten
from prism_reference.scene.description.types import Material

MOST_TRIANGLES = 40_000_000
NEAR_SCALE = 1e-4  # the near distance by the scene's diagonal when the camera has none
CHUNK = 1 << 20  # pixels shaded at once
NO_MATERIAL = -2  # the material plane of a triangle drawn without a material
ROLES = {
    "base_color_texture": COLOUR,
    "metallic_roughness_texture": DATA,
    "normal_texture": DATA,
    "occlusion_texture": DATA,
    "emissive_texture": COLOUR,
}


def camera_of(scene, node_index, size, near):
    """The rasterizer's camera (16,) float32 of a camera node at size (W, H): the node's
    world axes as they are (a roll kept), focal length from yfov over H."""
    node = scene.nodes[node_index]
    cam = scene.cameras[node.camera]
    if cam.kind != "perspective":
        raise ValueError(f"camera of node {node.name!r}: {cam.kind}, not perspective")
    linear = np.asarray(node.world, dtype=np.float64)[:3, :3]
    axes = [linear @ a for a in ([1.0, 0, 0], [0, 1.0, 0], [0, 0, -1.0])]
    right, up, forward = (a / np.linalg.norm(a) for a in axes)
    width, height = (int(n) for n in size)
    focal = (height / 2) / np.tan(cam.yfov / 2)
    near = cam.znear if cam.znear > 0 else near
    eye = np.asarray(node.world, dtype=np.float64)[:3, 3]
    tail = [focal, width / 2, height / 2, near]
    return np.concatenate([eye, right, up, forward, tail]).astype(np.float32)


def segments(scene):
    """Per drawn primitive in `flatten`'s order: (mesh, primitive, world), and the first
    vertex and triangle of each (P + 1,) with the totals last."""
    found, vertex, triangle = [], [0], [0]
    for mesh, world in draws(scene):
        for p, prim in enumerate(scene.meshes[mesh].primitives):
            found.append((mesh, p, world))
            vertex.append(vertex[-1] + len(prim.positions))
            triangle.append(triangle[-1] + len(prim.indices))
    return found, np.array(vertex, np.int64), np.array(triangle, np.int64)


def visibility(scene, camera_node, size, flat=None):
    """The nearest triangle per pixel (H, W) (-1: none) by `raster.frames.rasterize`,
    with the camera, the flattened scene and its diagonal."""
    if flat is None:
        flat = flatten(scene, MOST_TRIANGLES)
    p = flat["positions"]
    diagonal = float(np.linalg.norm(p.max(axis=0) - p.min(axis=0))) if len(p) else 1.0
    camera = camera_of(scene, camera_node, size, NEAR_SCALE * diagonal)
    width, height = (int(n) for n in size)
    frame = rasterize(
        {
            "positions": p,
            "indices": flat["indices"],
            "colors": np.zeros((len(p), 3), np.float32),
            "camera": camera,
            "size": (width, height),
        }
    )
    return {
        "tri": frame["tri"][:height, :width],
        "camera": camera,
        "flat": flat,
        "diagonal": diagonal,
        "size": (width, height),
    }


def material_of(scene, m):
    """The material of index m (glTF's default material for -1)."""
    return scene.materials[m] if m >= 0 else Material()


class Corners:
    """Per visible triangle its corners' world-space attributes, gathered by primitive."""

    def __init__(self, scene, seen, triangles, report):
        flat = seen["flat"]
        found, first_vertex, first_triangle = segments(scene)
        self.p = flat["positions"][flat["indices"][triangles]].astype(np.float64)
        self.material = flat["material"][triangles].astype(np.int64)
        count = len(triangles)
        self.normal = np.zeros((count, 3, 3))
        self.tangent = np.zeros((count, 3, 4))
        self.uv = [np.zeros((count, 3, 2)), np.zeros((count, 3, 2))]
        self.has_uv = [np.zeros(count, bool), np.zeros(count, bool)]
        self.has_tangent = np.zeros(count, bool)
        self.color = np.ones((count, 3, 4))
        face = unit_rows(
            np.cross(self.p[:, 1] - self.p[:, 0], self.p[:, 2] - self.p[:, 0])
        )
        self.face = face
        segment = np.searchsorted(first_triangle, triangles, side="right") - 1
        local = flat["indices"][triangles].astype(np.int64)
        local -= first_vertex[segment][:, None]
        sources = report.setdefault("tangents", {})
        computed = {}
        for s in np.unique(segment):
            pick = np.nonzero(segment == s)[0]
            mesh, p, world = found[s]
            prim = scene.meshes[mesh].primitives[p]
            self.gather(
                scene, prim, world, pick, local[pick], computed, sources, mesh, p
            )

    def gather(self, scene, prim, world, pick, li, computed, sources, mesh, p):
        """Fills the rows `pick` from one primitive drawn at `world`."""
        linear = np.asarray(world, dtype=np.float64)[:3, :3]
        inverse_t = np.linalg.inv(linear).T
        sign = 1.0 if np.linalg.det(linear) >= 0 else -1.0
        if prim.normals is not None:
            n = prim.normals[li].astype(np.float64) @ inverse_t.T
            self.normal[pick] = unit_rows(n)
        else:
            self.normal[pick] = self.face[pick][:, None, :]
        for k, values in enumerate((prim.uv0, prim.uv1)):
            if values is not None:
                self.uv[k][pick] = values[li]
                self.has_uv[k][pick] = True
        if prim.colors is not None:
            self.color[pick] = prim.colors[li]
        use = material_of(scene, prim.material).normal_texture
        if use is None:
            return
        name = f"mesh {mesh} primitive {p}"
        if prim.tangents is not None:
            t = prim.tangents
            sources[name] = "file"
        else:
            uv = prim.uv1 if use.uv == 1 else prim.uv0
            if uv is None:
                sources[name] = "none (no uv)"
                return
            if (mesh, p) not in computed:
                computed[(mesh, p)] = tangents(
                    prim.positions, prim.normals, uv, prim.indices
                )
            t = computed[(mesh, p)]
            sources[name] = "computed"
        t = t[li].astype(np.float64)
        self.tangent[pick, :, :3] = t[:, :, :3] @ linear.T
        self.tangent[pick, :, 3] = t[:, :, 3] * sign
        self.has_tangent[pick] = True


def interpolate(corner, b):
    """Corner values (N, 3, k) weighted by barycentrics b (N, 3)."""
    return np.einsum("nck,nc->nk", corner, b)


def pixel_geometry(camera, corners, rows, ys, xs):
    """Per pixel: position, view depth, barycentrics and their screen derivatives,
    from the pixel's ray through the triangle's plane (rows: its corner rows)."""
    cam = camera.astype(np.float64)
    eye, right, up, forward = cam[0:3], cam[3:6], cam[6:9], cam[9:12]
    focal, cx, cy = cam[12], cam[13], cam[14]
    px, py = xs + 0.5, ys + 0.5
    d = forward + np.outer((px - cx) / focal, right) + np.outer((cy - py) / focal, up)
    p = corners.p[rows]
    e1, e2 = p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]
    ng = np.cross(e1, e2)
    denom = np.sum(d * ng, axis=1)
    denom = np.where(denom == 0, 1e-30, denom)
    t = np.sum((p[:, 0] - eye) * ng, axis=1) / denom
    position = eye + t[:, None] * d
    d00, d01, d11 = (np.sum(a * b, axis=1) for a, b in ((e1, e1), (e1, e2), (e2, e2)))
    gram = d00 * d11 - d01 * d01
    gram = np.where(gram == 0, 1e-30, gram)

    def bary(w):
        c1, c2 = np.sum(w * e1, axis=1), np.sum(w * e2, axis=1)
        b1, b2 = (d11 * c1 - d01 * c2) / gram, (d00 * c2 - d01 * c1) / gram
        return np.stack([-(b1 + b2), b1, b2], axis=1)

    b = bary(position - p[:, 0])
    b[:, 0] += 1.0
    derivatives = []
    for step in (right / focal, -up / focal):
        dt = -t * np.sum(step * ng, axis=1) / denom
        derivatives.append(bary(t[:, None] * step + dt[:, None] * d))
    return position, t, b, derivatives[0], derivatives[1]


def texture_of(scene, use, role, cache):
    """(Texture, Sampler or None) of a TextureUse, decoded once into `cache`; None when
    the use or its texture names no image."""
    if use is None:
        return None
    texture = scene.textures[use.texture]
    if texture.image < 0:
        return None
    key = (texture.image, role)
    if key not in cache:
        cache[key] = Texture.of_image(scene.images[texture.image], role)
    sampler = scene.samplers[texture.sampler] if texture.sampler >= 0 else None
    return cache[key], sampler


def looked_up(scene, corners, r, weights, use, role, sample_fn, cache):
    """The filtered texel (k, 4) of a TextureUse at k pixels (corner rows r, weights
    (b, db/dx, db/dy)), and where it applies (the texture exists and the uv set too)."""
    found = texture_of(scene, use, role, cache)
    if found is None:
        return np.ones((len(r), 4)), np.zeros(len(r), bool)
    texture, sampler = found
    corner_uv = transformed(corners.uv[use.uv][r], use)
    b, bx, by = weights
    uv = interpolate(corner_uv, b)
    value = sample_fn(
        texture, sampler, uv, interpolate(corner_uv, bx), interpolate(corner_uv, by)
    )
    has = corners.has_uv[use.uv][r]
    return np.where(has[:, None], value, 1.0), has


def mapped_normal(corners, r, b, n, texel, scale):
    """The normal map's normal: the texel's (x scale, y scale, z) through the tangent
    frame (tangent, cross(n, tangent) w, n), made unit."""
    tangent = interpolate(corners.tangent[r][:, :, :3], b)
    tangent = unit_rows(tangent - n * np.sum(n * tangent, axis=1, keepdims=True))
    w = np.where(corners.tangent[r][:, 0, 3] < 0, -1.0, 1.0)[:, None]
    side = np.cross(n, tangent) * w
    t = texel[:, :3] * 2.0 - 1.0
    t[:, :2] *= scale
    return unit_rows(t[:, :1] * tangent + t[:, 1:2] * side + t[:, 2:3] * n)


def shade_material(scene, material, corners, r, weights, n, sample_fn, cache):
    """The planes base_color, alpha, metallic, roughness, occlusion, emissive and normal
    of k pixels of one material."""
    b = weights[0]

    def look(name):
        return looked_up(
            scene,
            corners,
            r,
            weights,
            getattr(material, name),
            ROLES[name],
            sample_fn,
            cache,
        )

    colour = interpolate(corners.color[r], b) * material.base_color
    texel, _ = look("base_color_texture")
    colour = colour * texel
    mr, _ = look("metallic_roughness_texture")
    occlusion, _ = look("occlusion_texture")
    glow, _ = look("emissive_texture")
    normal = n
    if material.normal_texture is not None:
        texel, has = look("normal_texture")
        has &= corners.has_tangent[r]
        if has.any():
            bent = mapped_normal(corners, r, b, n, texel, material.normal_scale)
            normal = np.where(has[:, None], bent, n)
    return {
        "base_color": colour[:, :3],
        "alpha": colour[:, 3],
        "metallic": material.metallic * mr[:, 2],
        "roughness": material.roughness * mr[:, 1],
        "occlusion": 1.0 + material.occlusion_strength * (occlusion[:, 0] - 1.0),
        "emissive": material.emissive * material.emissive_strength * glow[:, :3],
        "normal": normal,
    }


def is_transparent(material):
    """BLEND, or KHR_materials_transmission with a factor above 0."""
    return material.alpha_mode == "BLEND" or (transmission_factor(material) or 0) > 0


def shade_chunk(scene, seen, corners, rows, ys, xs, planes, sample_fn, cache, counts):
    """Writes every plane at the pixels (ys, xs) whose corner rows are `rows`."""
    camera = seen["camera"]
    position, depth, b, bx, by = pixel_geometry(camera, corners, rows, ys, xs)
    to_eye = camera[0:3].astype(np.float64) - position
    face = corners.face[rows]
    n = unit_rows(interpolate(corners.normal[rows], b))
    values = {"normal": n.copy()}
    material_index = corners.material[rows]
    flip = np.zeros(len(rows), bool)
    for m in np.unique(material_index):
        pick = np.nonzero(material_index == m)[0]
        material = material_of(scene, m)
        weights = (b[pick], bx[pick], by[pick])
        got = shade_material(
            scene, material, corners, rows[pick], weights, n[pick], sample_fn, cache
        )
        for name, value in got.items():
            if name not in values:
                values[name] = np.zeros((len(rows),) + value.shape[1:])
            values[name][pick] = value
        if material.double_sided:
            flip[pick] = np.sum(face[pick] * to_eye[pick], axis=1) < 0
        if material.alpha_mode == "MASK":
            counts["mask_below_cutoff"] += int(
                np.sum(got["alpha"] < material.alpha_cutoff)
            )
        planes["transparent"][ys[pick], xs[pick]] = is_transparent(material)
    sign = np.where(flip, -1.0, 1.0)[:, None]
    values["normal"] = values["normal"] * sign
    values["geometric_normal"] = face * sign
    values["position"] = position
    values["depth"] = depth
    values["uv"] = interpolate(corners.uv[0][rows], b)
    for name, value in values.items():
        planes[name][ys, xs] = value
    planes["material"][ys, xs] = np.where(
        material_index >= 0, material_index, NO_MATERIAL
    )


PLANES = {
    "depth": (),
    "position": (3,),
    "geometric_normal": (3,),
    "normal": (3,),
    "base_color": (3,),
    "alpha": (),
    "metallic": (),
    "roughness": (),
    "occlusion": (),
    "emissive": (3,),
    "uv": (2,),
}


def surface(
    scene, camera_node, size, filter="anisotropic", seen=None, cache=None, report=None
):
    """The surface planes (H, W, ...) float32 of the scene from a camera node at size
    (W, H), textures filtered by `filter` ("nearest", "trilinear", "anisotropic")."""
    seen = seen if seen is not None else visibility(scene, camera_node, size)
    cache = cache if cache is not None else {}
    report = report if report is not None else {}
    tri = seen["tri"]
    shape = tri.shape
    planes = {k: np.zeros(shape + extra, np.float32) for k, extra in PLANES.items()}
    planes["covered"] = tri >= 0
    planes["material"] = np.full(shape, -1, np.int32)
    planes["transparent"] = np.zeros(shape, bool)
    ys, xs = np.nonzero(planes["covered"])
    triangles, rows = np.unique(tri[ys, xs], return_inverse=True)
    corners = Corners(scene, seen, triangles, report)
    counts = {"mask_below_cutoff": 0}
    for start in range(0, len(ys), CHUNK):
        part = slice(start, start + CHUNK)
        shade_chunk(
            scene,
            seen,
            corners,
            rows[part],
            ys[part],
            xs[part],
            planes,
            FILTERS[filter],
            cache,
            counts,
        )
    report |= counts
    return planes
