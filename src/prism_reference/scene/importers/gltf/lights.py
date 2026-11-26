"""glTF cameras and KHR_lights_punctual lights."""

import numpy as np

from prism_reference.scene.description.types import Camera, Light, Note


def lights(doc):
    """The Light of every punctual light of the file."""
    found = []
    entries = doc.get("extensions", {}).get("KHR_lights_punctual", {}).get("lights", [])
    for entry in entries:
        spot = entry.get("spot", {})
        found.append(
            Light(
                kind=entry["type"],
                color=np.array(entry.get("color", [1.0, 1.0, 1.0]), np.float64),
                intensity=float(entry.get("intensity", 1.0)),
                range=float(entry["range"]) if "range" in entry else None,
                inner_cone=float(spot.get("innerConeAngle", 0.0)),
                outer_cone=float(spot.get("outerConeAngle", np.pi / 4)),
            )
        )
    return found


def _optional(entry, key):
    """A float value, or None when absent."""
    return float(entry[key]) if key in entry else None


def cameras(doc):
    """The Camera of every camera of the file."""
    found = []
    for entry in doc.get("cameras", []):
        kind = entry["type"]
        values = entry.get(kind, {})
        camera = Camera(kind=kind, znear=float(values.get("znear", 0.0)))
        camera.zfar = _optional(values, "zfar")
        if kind == "perspective":
            camera.yfov = float(values.get("yfov", 0.0))
            camera.aspect = _optional(values, "aspectRatio")
        else:
            camera.xmag = float(values.get("xmag", 0.0))
            camera.ymag = float(values.get("ymag", 0.0))
        found.append(camera)
    return found


def lights_and_cameras(doc):
    """Lights, cameras and the notes of what was read."""
    found_lights, found_cameras = lights(doc), cameras(doc)
    notes = []
    if found_lights:
        notes.append(Note("used", "KHR_lights_punctual", len(found_lights)))
    if found_cameras:
        notes.append(Note("used", "cameras", len(found_cameras)))
    return found_lights, found_cameras, notes
