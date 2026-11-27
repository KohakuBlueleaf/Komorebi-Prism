"""The table entry of a converted scene: its one view from the file's camera, its light
point and its lighting defaults with the file's sun and lamps."""

import numpy as np

from prism_reference.scene.description.types import Note

VIEW = "camera"
ASPECT = 16 / 9  # the picture's W / H when neither the sidecar nor the camera gives one
ROLL_DEGREES = 1.0
ENVIRONMENT = "kloppenheim_05"
LIGHTING = {
    "environment": ENVIRONMENT,
    "turn": 0.0,
    "sun_to_sky": 5.0,
    "ambient": [0.35, 0.33, 0.3],
    "lamp_scale": 1.0,
    "emissive_scale": 1.0,
    "exposure": 1.0,
    "shadow_bias": 3.0,
}
# Lighting lengths as fractions of the diagonal of the mesh's bounding box.
BY_DIAGONAL = {"merge_distance": 0.01, "radius": 0.2, "size": 0.002}


def unit(v):
    """A float64 3-vector scaled to length 1."""
    v = np.asarray(v, dtype=np.float64)
    return v / np.linalg.norm(v)


def camera_node(scene, name=None):
    """The view's node index: the node named `name`, else the sidecar's render camera,
    else the first node with a camera; ValueError when there is none."""
    if name is not None:
        for i, node in enumerate(scene.nodes):
            if node.name == name:
                if node.camera == -1:
                    raise ValueError(f"node {name!r} holds no camera")
                return i
        raise ValueError(f"no node named {name!r}")
    if scene.render is not None and scene.render.camera != -1:
        return scene.render.camera
    for i, node in enumerate(scene.nodes):
        if node.camera != -1:
            return i
    raise ValueError("the file holds no camera")


def view_of(scene, name=None):
    """The `views` entry {"camera": {eye, target, fov, near?}} and its notes."""
    index = camera_node(scene, name)
    node = scene.nodes[index]
    cam = scene.cameras[node.camera]
    if cam.kind != "perspective":
        raise ValueError(f"camera of node {node.name!r}: {cam.kind}, not perspective")
    world = np.asarray(node.world, dtype=np.float64)
    eye = world[:3, 3]
    forward = unit(world[:3, :3] @ [0.0, 0.0, -1.0])
    aspect = ASPECT
    if scene.render is not None and np.all(scene.render.size > 0):
        aspect = float(scene.render.size[0]) / float(scene.render.size[1])
    elif cam.aspect:
        aspect = float(cam.aspect)
    fov = cam.yfov
    if aspect >= 1:
        fov = 2.0 * np.arctan(aspect * np.tan(cam.yfov / 2.0))
    spec = {
        "eye": [float(x) for x in eye],
        "target": [float(x) for x in eye + forward],
        "fov": float(np.degrees(fov)),
    }
    if cam.znear > 0:
        spec["near"] = float(cam.znear)
    notes = []
    across = np.cross([0.0, 1.0, 0.0], forward)
    if np.linalg.norm(across) > 0:
        up = unit(world[:3, :3] @ [0.0, 1.0, 0.0])
        off = np.degrees(np.arcsin(min(1.0, abs(float(up @ unit(across))))))
        if off > ROLL_DEGREES:
            notes.append(Note("dropped", "camera roll", 1, f"{off:.2f} degrees"))
    if cam.shift_x or cam.shift_y:
        shift = f"{cam.shift_x:.4f}, {cam.shift_y:.4f} of the fitted side"
        notes.append(Note("dropped", "camera shift", 1, shift))
    return {VIEW: spec}, {"node": node.name, "aspect": aspect} | spec, notes


def lights_of(scene):
    """The lighting's `sun` (first directional light) and `lights` (point and spot
    lights as points) from the nodes holding lights, and their notes."""
    sun, lamps, spots, areas = None, [], 0, 0
    for node in scene.nodes:
        if node.light == -1:
            continue
        light = scene.lights[node.light]
        world = np.asarray(node.world, dtype=np.float64)
        colour = [float(x) for x in light.color]
        if light.kind == "directional":
            if sun is None:
                direction = unit(world[:3, :3] @ [0.0, 0.0, -1.0])
                sun = {"direction": [float(x) for x in direction], "colour": colour}
        elif light.kind in ("point", "spot"):
            spots += light.kind == "spot"
            lamps.append(
                {"position": [float(x) for x in world[:3, 3]], "colour": colour}
            )
        else:
            areas += 1
    notes = []
    if spots:
        notes.append(Note("dropped", "spot cone", spots, "drawn as a point light"))
    if areas:
        notes.append(Note("dropped", "area lights", areas))
    return sun, lamps, notes


def entry_of(scene, positions, triangles, camera=None, licence="", attribution=""):
    """The table entry (the layout of `public_scenes.json`) of a converted scene, the
    view's report and the notes; positions: the written mesh's vertices."""
    p = np.asarray(positions, dtype=np.float64)
    lo, hi = p.min(axis=0), p.max(axis=0)
    centre, diagonal = (lo + hi) / 2, float(np.linalg.norm(hi - lo))
    views, view, notes = view_of(scene, camera)
    lighting = dict(LIGHTING)
    lighting |= {k: f * diagonal for k, f in BY_DIAGONAL.items()}
    if scene.render is not None:
        lighting["exposure"] = float(2.0**scene.render.exposure)
    sun, lamps, light_notes = lights_of(scene)
    if sun is not None:
        lighting["sun"] = sun
    if lamps:
        lighting["lights"] = lamps
    entry = {
        "title": "",
        "page": "",
        "licence": licence,
        "attribution": attribution,
        "triangles": int(triangles),
        "files": [],
        "meshes": [],
        "materials": {},
        "views": views,
        "light": [float(centre[0]), float(hi[1]), float(centre[2])],
        "lighting": lighting,
    }
    return entry, view, notes + light_notes
