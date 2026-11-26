"""The consistency of a scene description: indices, attribute lengths, finite values, no
parent cycle; the first failure is a ValueError naming it."""

import numpy as np

from prism_reference.scene.description.types import Scene

TEXTURE_FIELDS = (
    "base_color_texture",
    "metallic_roughness_texture",
    "normal_texture",
    "occlusion_texture",
    "emissive_texture",
)
ATTRIBUTES = ("normals", "tangents", "uv0", "uv1", "colors")


def _index(value, size, what, none_ok=True):
    """Raises unless `value` is in range(size), or -1 when `none_ok`."""
    if none_ok and value == -1:
        return
    if not 0 <= value < size:
        raise ValueError(f"{what}: index {value} out of 0..{size - 1}")


def _finite(array, what):
    """Raises when `array` holds a non-finite value."""
    if not np.isfinite(array).all():
        raise ValueError(f"{what}: not finite")


def _nodes(scene):
    """Indices, finite matrices and no parent cycle of every node."""
    count = len(scene.nodes)
    for i, node in enumerate(scene.nodes):
        what = f"node {i} ({node.name})"
        _index(node.parent, count, f"{what} parent")
        _index(node.mesh, len(scene.meshes), f"{what} mesh")
        _index(node.camera, len(scene.cameras), f"{what} camera")
        _index(node.light, len(scene.lights), f"{what} light")
        _finite(node.local, f"{what} local matrix")
        _finite(node.world, f"{what} world matrix")
        if node.instances is not None:
            _finite(node.instances, f"{what} instances")
    for i in range(count):
        seen, at = set(), i
        while at != -1:
            if at in seen:
                raise ValueError(f"node {i}: parent cycle through node {at}")
            seen.add(at)
            at = scene.nodes[at].parent


def _meshes(scene):
    """Each primitive's material, vertex count of its attributes, indices and positions."""
    for m, mesh in enumerate(scene.meshes):
        for p, prim in enumerate(mesh.primitives):
            what = f"mesh {m} ({mesh.name}) primitive {p}"
            _index(prim.material, len(scene.materials), f"{what} material")
            vertices = len(prim.positions)
            for name in ATTRIBUTES:
                value = getattr(prim, name)
                if value is not None and len(value) != vertices:
                    raise ValueError(
                        f"{what} {name}: {len(value)} entries for {vertices} vertices"
                    )
            if len(prim.indices) and int(prim.indices.max()) >= vertices:
                raise ValueError(
                    f"{what} indices: {int(prim.indices.max())} at or past "
                    f"{vertices} vertices"
                )
            _finite(prim.positions, f"{what} positions")


def _materials(scene):
    """Every texture reference of a material, and each texture's image and sampler."""
    for m, material in enumerate(scene.materials):
        for name in TEXTURE_FIELDS:
            use = getattr(material, name)
            if use is not None:
                _index(
                    use.texture,
                    len(scene.textures),
                    f"material {m} ({material.name}) {name}",
                    False,
                )
    for t, texture in enumerate(scene.textures):
        _index(texture.image, len(scene.images), f"texture {t} image")
        _index(texture.sampler, len(scene.samplers), f"texture {t} sampler")


def check(scene: Scene):
    """Raises ValueError naming the first inconsistency of `scene`."""
    _nodes(scene)
    _meshes(scene)
    _materials(scene)
    if scene.render is not None:
        _index(scene.render.camera, len(scene.nodes), "render camera node")
