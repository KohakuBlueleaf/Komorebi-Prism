"""A scene description drawn into one set of world-space arrays: every mesh node once at its
world matrix, or once at each of its instances."""

import numpy as np

from prism_reference.scene.description.types import Scene


def draws(scene: Scene):
    """Each drawn copy as (mesh index, (4, 4) float64 world matrix)."""
    found = []
    for node in scene.nodes:
        if node.mesh == -1:
            continue
        if node.instances is not None:
            found.extend((node.mesh, m.astype(np.float64)) for m in node.instances)
        else:
            found.append((node.mesh, node.world))
    return found


def mesh_triangles(mesh):
    """The triangles of a mesh: the sum over its primitives."""
    return sum(len(prim.indices) for prim in mesh.primitives)


def drawn_triangles(scene: Scene):
    """The triangles `flatten` draws, counted without making an array."""
    total = 0
    for node in scene.nodes:
        if node.mesh != -1:
            copies = 1 if node.instances is None else len(node.instances)
            total += copies * mesh_triangles(scene.meshes[node.mesh])
    return total


def flatten(scene: Scene, most_triangles: int):
    """World-space positions, unit normals, uv0, uv1, indices and per-triangle material."""
    total = drawn_triangles(scene)
    if total > most_triangles:
        raise ValueError(
            f"flatten: {total} triangles drawn, more than the {most_triangles} allowed"
        )
    copies = draws(scene)
    vertices = sum(
        len(p.positions) for m, _ in copies for p in scene.meshes[m].primitives
    )
    positions = np.zeros((vertices, 3), np.float32)
    normals = np.zeros((vertices, 3), np.float32)
    uv0 = np.zeros((vertices, 2), np.float32)
    uv1 = np.zeros((vertices, 2), np.float32)
    indices = np.zeros((total, 3), np.uint32)
    material = np.zeros(total, np.int32)
    v_at = t_at = 0
    for mesh, world in copies:
        linear = world[:3, :3]
        normal_matrix = np.linalg.inv(linear).T
        flip = np.linalg.det(linear) < 0
        for prim in scene.meshes[mesh].primitives:
            count, tris = len(prim.positions), len(prim.indices)
            p = prim.positions.astype(np.float64)
            positions[v_at : v_at + count] = p @ linear.T + world[:3, 3]
            if prim.normals is not None:
                n = prim.normals.astype(np.float64) @ normal_matrix.T
                length = np.linalg.norm(n, axis=1, keepdims=True)
                normals[v_at : v_at + count] = n / np.where(length > 0, length, 1)
            if prim.uv0 is not None:
                uv0[v_at : v_at + count] = prim.uv0
            if prim.uv1 is not None:
                uv1[v_at : v_at + count] = prim.uv1
            corners = prim.indices[:, [0, 2, 1]] if flip else prim.indices
            indices[t_at : t_at + tris] = corners + np.uint32(v_at)
            material[t_at : t_at + tris] = prim.material
            v_at += count
            t_at += tris
    return {
        "positions": positions,
        "normals": normals,
        "uv0": uv0,
        "uv1": uv1,
        "indices": indices,
        "material": material,
    }
