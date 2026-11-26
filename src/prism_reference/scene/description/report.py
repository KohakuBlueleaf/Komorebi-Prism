"""What a scene description holds, as counts: a JSON-ready dict and its terminal lines."""

from prism_reference.scene.description.check import TEXTURE_FIELDS
from prism_reference.scene.description.flatten import drawn_triangles, mesh_triangles
from prism_reference.scene.description.types import Scene

ALPHA_MODES = ("OPAQUE", "MASK", "BLEND")
LIGHT_KINDS = ("directional", "point", "spot", "area")


def coverage(scene: Scene):
    """Counts of what `scene` holds, its drawn triangles and its notes by kind."""
    notes = {}
    for note in scene.notes:
        notes.setdefault(note.kind, []).append(
            {"what": note.what, "count": note.count, "detail": note.detail}
        )
    lights = {kind: sum(lt.kind == kind for lt in scene.lights) for kind in LIGHT_KINDS}
    return {
        "source": dict(scene.source),
        "nodes": len(scene.nodes),
        "meshes": len(scene.meshes),
        "primitives": sum(len(m.primitives) for m in scene.meshes),
        "stored_triangles": sum(mesh_triangles(m) for m in scene.meshes),
        "drawn_triangles": drawn_triangles(scene),
        "instanced_nodes": sum(n.instances is not None for n in scene.nodes),
        "file_instanced_nodes": scene.source.get("file", {}).get("instanced_nodes"),
        "instances": sum(
            len(n.instances) for n in scene.nodes if n.instances is not None
        ),
        "materials": len(scene.materials),
        "materials_by_alpha": {
            mode: sum(m.alpha_mode == mode for m in scene.materials)
            for mode in ALPHA_MODES
        },
        "materials_with_texture": {
            name: sum(getattr(m, name) is not None for m in scene.materials)
            for name in TEXTURE_FIELDS
        },
        "images": len(scene.images),
        "image_largest_sides": [max(i.width, i.height) for i in scene.images],
        "lights": lights,
        "punctual_lights": lights["directional"] + lights["point"] + lights["spot"],
        "cameras": len(scene.cameras),
        "moving_nodes": sum(n.moving for n in scene.nodes),
        "notes": notes,
    }


def text(report):
    """The report as lines for a terminal."""
    lines = [f"source: {report['source']}"]
    for key in (
        "nodes",
        "meshes",
        "primitives",
        "stored_triangles",
        "drawn_triangles",
        "instanced_nodes",
        "instances",
        "materials",
        "images",
        "punctual_lights",
        "cameras",
        "moving_nodes",
    ):
        lines.append(f"{key}: {report[key]:,}")
    if report["file_instanced_nodes"] is not None:
        lines.append(f"file_instanced_nodes: {report['file_instanced_nodes']:,}")
    for key in ("materials_by_alpha", "materials_with_texture", "lights"):
        lines.append(f"{key}: " + ", ".join(f"{k} {v}" for k, v in report[key].items()))
    sides = report["image_largest_sides"]
    if sides:
        lines.append(f"image largest sides: {min(sides)} to {max(sides)}")
    for kind, entries in report["notes"].items():
        for e in entries:
            detail = f" ({e['detail']})" if e["detail"] else ""
            lines.append(f"{kind}: {e['what']} x{e['count']}{detail}")
    return lines
