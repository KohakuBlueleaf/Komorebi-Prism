"""The record of a converted scene's file kept in its table entry (`source`): the file,
its format and bytes, and what it holds as the scene description reads it."""

from pathlib import Path

from prism_reference.scene.description.flatten import drawn_triangles, mesh_triangles


def source_of(path, scene):
    """`source` of the glTF file `path` read as the description `scene`: the file, its
    format, its bytes, the drawn mesh nodes (objects), their copies (instances), the
    meshes they draw and those meshes' triangles stored once and drawn."""
    path = Path(path).resolve()
    drawn = [node for node in scene.nodes if node.mesh != -1]
    meshes = sorted({node.mesh for node in drawn})
    return {
        "file": str(path),
        "format": path.suffix.lstrip(".").lower(),
        "bytes": path.stat().st_size,
        "objects": len(drawn),
        "instances": sum(
            1 if node.instances is None else len(node.instances) for node in drawn
        ),
        "meshes": len(meshes),
        "stored_triangles": sum(mesh_triangles(scene.meshes[m]) for m in meshes),
        "drawn_triangles": drawn_triangles(scene),
    }
