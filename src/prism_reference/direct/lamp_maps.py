"""The lamps' shadow maps: a lamp's faces by its shape (a cosine lobe's hemicube: a front
face and four halves; a point's cube; a spot's one map of its cone), each face's camera
with a guard band, and the map (1/z) of a face drawn as the sun's is."""

import numpy as np

from prism_reference.direct.lamps import lamp_shapes
from prism_reference.direct.transmit import transmittance
from prism_reference.raster.frames import rasterize, rasterize_shaded
from prism_reference.scene.frame import TILE

F = np.float32
LAMP_SIDE = 512  # a lobe's or a point's face
SPOT_SIDE = 1024  # a spot's map
GUARD = 16 / 512  # the guard band past a face's edge, a share of its side
NEAR = 1e-4  # a face's near distance, a share of the lamps' radius
SPOT_MARGIN = np.radians(1.0)  # past a spot's outer cone
CUBE = ("+x", "-x", "+y", "-y", "+z", "-z")
HEMICUBE = ("front", "+r", "-r", "+u", "-u")


def lamp_kind(shape):
    """'point' (no shape), 'lobe' (a cosine lobe: offset and square 0) or 'spot'."""
    if shape[3] == 0:
        return "point"
    if shape[4] == 0 and shape[5] == 0:
        return "lobe"
    return "spot"


def basis(forward):
    """Right, up, forward (3, 3) float64 about a unit `forward` (right = y x forward)."""
    f = np.asarray(forward, np.float64)
    f = f / np.linalg.norm(f)
    helper = np.array([0.0, 1.0, 0.0]) if abs(f[1]) < 0.9 else np.array([1.0, 0, 0])
    right = np.cross(helper, f)
    right /= np.linalg.norm(right)
    return right, np.cross(f, right), f


def face_camera(eye, right, up, forward, focal, centre, size, near):
    """A camera (16,) float32: eye, right, up, forward, focal, the frame's centre
    (cx, cy) and the near distance."""
    tail = [focal, centre[0], centre[1], near]
    return np.concatenate([eye, right, up, forward, tail]).astype(F)


def tiles_up(n):
    """n rounded up to whole tiles."""
    return -(-int(n) // TILE) * TILE


def lamp_faces(lights):
    """Every lamp's faces in order: dicts of lamp, kind, face, camera (16,) float32 and
    size (W, H). A face of side S keeps S GUARD texels past its 90 degree edge; a
    hemicube's side face is the half towards the front (its top rows) and the band.
    Lamps found among emissive triangles (no `lamp_shape`) have none."""
    if "lamp_shape" not in lights:
        return []
    shapes = lamp_shapes(lights)
    near = F(NEAR * float(lights["radius"]))
    out = []
    for k, (position, shape) in enumerate(zip(lights["lamp_position"], shapes)):
        eye = np.asarray(position, np.float64)
        kind = lamp_kind(shape)
        if kind == "spot":
            side = SPOT_SIDE
            cos_outer = float(-shape[4] / shape[3])
            half = np.arccos(np.clip(cos_outer, -1, 1)) + SPOT_MARGIN
            r, u, f = basis(shape[0:3])
            focal = (side / 2 - GUARD * side) / np.tan(min(half, np.radians(85)))
            camera = face_camera(eye, r, u, f, focal, (side / 2, side / 2), side, near)
            out.append(
                {
                    "lamp": k,
                    "kind": kind,
                    "face": "cone",
                    "camera": camera,
                    "size": (side, side),
                }
            )
            continue
        side = LAMP_SIDE
        focal = side / 2 - GUARD * side
        if kind == "point":
            r, u, f = np.eye(3)
            frames = {
                "+x": (-f, u, r),
                "-x": (f, u, -r),
                "+y": (r, -f, u),
                "-y": (r, f, -u),
                "+z": (r, u, f),
                "-z": (-r, u, -f),
            }
            for name in CUBE:
                fr, fu, ff = frames[name]
                camera = face_camera(
                    eye, fr, fu, ff, focal, (side / 2, side / 2), side, near
                )
                out.append(
                    {
                        "lamp": k,
                        "kind": kind,
                        "face": name,
                        "camera": camera,
                        "size": (side, side),
                    }
                )
            continue
        r, u, f = basis(shape[0:3])
        height = tiles_up(side / 2 + GUARD * side)
        forwards = {"front": f, "+r": r, "-r": -r, "+u": u, "-u": -u}
        for name in HEMICUBE:
            ff = forwards[name]
            # a side face's up is the front: its top rows are the half towards it
            up = u if name == "front" else f
            right = np.cross(up, ff)
            camera = face_camera(
                eye, right, up, ff, focal, (side / 2, side / 2), side, near
            )
            size = (side, side) if name == "front" else (side, height)
            out.append(
                {"lamp": k, "kind": kind, "face": name, "camera": camera, "size": size}
            )
    return out


def face_pages(face):
    """A face's pages of 32 x 32 texels: (W / 32) (H / 32)."""
    width, height = face["size"]
    return (width // TILE) * (height // TILE)


def lamp_pages(lights):
    """The pages of every lamp's faces."""
    return sum(face_pages(face) for face in lamp_faces(lights))


def face_view(scene, face):
    """The view of `scene` a face draws: its camera at its size, no colour."""
    return {
        "positions": scene["positions"],
        "indices": scene["indices"],
        "colors": np.zeros((len(scene["positions"]), 3), dtype=F),
        "camera": face["camera"],
        "light": np.zeros(3, dtype=F),
        "size": tuple(face["size"]),
    }


def face_map(scene, face, materials=None):
    """The 1/z (H, W) of `scene` from a face's camera at its size, drawn as the sun's
    shadow map is (rasterize_shaded with materials, else rasterize)."""
    view = face_view(scene, face)
    if materials is None:
        return rasterize(view)["depth"]
    return rasterize_shaded(view, materials)["depth"]


def face_transmit(scene, face, materials, depth):
    """A face's T (H, W, 3) beside its map `depth` (transmittance)."""
    return transmittance(face_view(scene, face), materials, depth)[0]
