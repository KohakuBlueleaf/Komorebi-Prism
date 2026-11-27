"""Helpers the export imports inside Blender: the world length of one uv unit on the
triangles of a material, its copies counted, as the median and the spread."""

import numpy

STEP = 0.002  # bin width of the log length
SMALLEST = 1e-14  # a uv or world area under this: the triangle is not counted
SPREAD = (0.1, 0.9)


def layer_of(mesh, uv_name):
    """The uv layer `uv_name` of a mesh, else its active render layer, else None."""
    layers = mesh.uv_layers
    if uv_name and layers.get(uv_name) is not None:
        return layers[uv_name]
    return next((u for u in layers if u.active_render), layers.active)


def triangle_lengths(mesh, slots, uv_name):
    """sqrt(world area / uv area) of the mesh's triangles drawn with a slot of
    `slots`, in the mesh's own space."""
    layer = layer_of(mesh, uv_name)
    if layer is None:
        return numpy.empty(0)
    mesh.calc_loop_triangles()
    count = len(mesh.loop_triangles)
    loops = numpy.empty(count * 3, numpy.int32)
    mesh.loop_triangles.foreach_get("loops", loops)
    indices = numpy.empty(count, numpy.int32)
    mesh.loop_triangles.foreach_get("material_index", indices)
    chosen = numpy.isin(indices, list(slots))
    loops = loops.reshape(-1, 3)[chosen]
    corners = numpy.empty(len(mesh.loops), numpy.int32)
    mesh.loops.foreach_get("vertex_index", corners)
    points = numpy.empty(len(mesh.vertices) * 3, numpy.float64)
    mesh.vertices.foreach_get("co", points)
    points = points.reshape(-1, 3)[corners[loops]]
    uvs = numpy.empty(len(mesh.loops) * 2, numpy.float64)
    layer.data.foreach_get("uv", uvs)
    uvs = uvs.reshape(-1, 2)[loops]
    world = numpy.linalg.norm(
        numpy.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0]), axis=1
    )
    a, b = uvs[:, 1] - uvs[:, 0], uvs[:, 2] - uvs[:, 0]
    flat = numpy.abs(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0])
    kept = (flat > SMALLEST) & (world > SMALLEST)
    return numpy.sqrt(world[kept] / flat[kept])


def scales(matrices):
    """The length scale |det|^(1/3) of each copy's world matrix."""
    blocks = numpy.array([[list(r)[:3] for r in list(m)[:3]] for m in matrices])
    return numpy.abs(numpy.linalg.det(blocks)) ** (1 / 3)


class Lengths:
    """Metres a uv unit for (material, uv map), over the drawn triangles of `found`."""

    def __init__(self, found):
        self.found = found or {}
        self.cache = {}

    def of(self, material, uv_name):
        """{"metres", "p10", "p90", "triangles"} of a material; metres None when no
        drawn triangle of it has a uv area."""
        key = (material.name_full, uv_name)
        if key not in self.cache:
            self.cache[key] = self.measure(material, uv_name)
        return self.cache[key]

    def measure(self, material, uv_name):
        """The counted log lengths of every copy's triangles, as their quantiles."""
        bins = {}
        for entry in self.found.values():
            mesh = entry["source"]
            if mesh is None:
                continue
            slots = [i for i, m in enumerate(mesh.materials) if m == material]
            if not slots:
                continue
            lengths = triangle_lengths(mesh, slots, uv_name)
            if not len(lengths):
                continue
            own, own_counts = numpy.unique(
                numpy.rint(numpy.log(lengths) / STEP).astype(numpy.int64),
                return_counts=True,
            )
            copy = numpy.rint(numpy.log(scales(entry["matrices"])) / STEP)
            shifts, copies = numpy.unique(copy.astype(numpy.int64), return_counts=True)
            for shift, times in zip(shifts, copies, strict=True):
                for b, n in zip(own + shift, own_counts * times, strict=True):
                    bins[int(b)] = bins.get(int(b), 0) + int(n)
        if not bins:
            return {"metres": None, "p10": None, "p90": None, "triangles": 0}
        order = sorted(bins)
        counts = numpy.cumsum([bins[b] for b in order])
        total = int(counts[-1])

        def quantile(q):
            at = order[int(numpy.searchsorted(counts, q * total))]
            return round(float(numpy.exp(at * STEP)), 4)

        low, high = SPREAD
        return {
            "metres": quantile(0.5),
            "p10": quantile(low),
            "p90": quantile(high),
            "triangles": total,
        }
