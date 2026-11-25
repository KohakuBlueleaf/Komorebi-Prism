"""A pose (position, yaw, pitch, field of view) from a camera's 16 numbers, and the 16
numbers of a pose; y is up, yaw about y from +z toward +x, pitch above the horizon, the
field of view in degrees across the reference WIDTH (a view's `fov`)."""

import math

import numpy as np

from prism_reference.scene.frame import WIDTH

EYE, RIGHT, UP, AHEAD = slice(0, 3), slice(3, 6), slice(6, 9), slice(9, 12)
FOCAL = 12
PITCH_LIMIT = math.radians(89.0)
FOV_LEAST, FOV_MOST = 0.5, 179.0  # degrees: the ends tried on the card (viewer guide)


def fov_of(focal):
    """The field of view in degrees of a camera's focal at the reference WIDTH."""
    return math.degrees(2.0 * math.atan((WIDTH / 2) / float(focal)))


def focal_of(fov):
    """The focal at the reference WIDTH of a field of view in degrees."""
    return (WIDTH / 2) / math.tan(math.radians(fov) / 2)


def pose_of(camera):
    """The pose of a camera: its eye, the yaw and the pitch of its view direction, the
    field of view of its focal."""
    camera = np.asarray(camera, dtype=np.float64)
    fx, fy, fz = camera[AHEAD] / np.linalg.norm(camera[AHEAD])
    return {
        "position": [float(value) for value in camera[EYE]],
        "yaw": math.atan2(fx, fz),
        "pitch": math.asin(max(-1.0, min(1.0, fy))),
        "fov": fov_of(camera[FOCAL]),
    }


def camera_of(own, pose):
    """The 16 numbers of `pose`: its eye and the axes from yaw and pitch (right = ahead
    x y, up = right x ahead), the focal of its field of view (the camera `own`'s without
    one); centre and near those of `own`."""
    yaw, pitch = pose["yaw"], pose["pitch"]
    ahead = np.array(
        [
            math.cos(pitch) * math.sin(yaw),
            math.sin(pitch),
            math.cos(pitch) * math.cos(yaw),
        ]
    )
    right = np.cross(ahead, np.array([0.0, 1.0, 0.0]))
    right /= np.linalg.norm(right)
    up = np.cross(right, ahead)
    camera = np.array(own, dtype=np.float32)
    camera[EYE] = pose["position"]
    camera[RIGHT], camera[UP], camera[AHEAD] = right, up, ahead
    if pose.get("fov") is not None:
        camera[FOCAL] = focal_of(pose["fov"])
    return camera


def parsed(body):
    """A pose from a request's JSON: three finite numbers, a yaw and a pitch (clamped
    to PITCH_LIMIT), a field of view within FOV_LEAST and FOV_MOST or none (None: the
    one before); ValueError with the reason otherwise."""
    position = [float(value) for value in body["position"]]
    yaw, pitch = float(body["yaw"]), float(body["pitch"])
    if len(position) != 3 or not all(map(math.isfinite, [*position, yaw, pitch])):
        raise ValueError("a pose is 3 finite numbers, a yaw and a pitch")
    pitch = max(-PITCH_LIMIT, min(PITCH_LIMIT, pitch))
    fov = body.get("fov")
    if fov is not None:
        fov = float(fov)
        if not FOV_LEAST <= fov <= FOV_MOST:
            raise ValueError(
                f"a field of view is {FOV_LEAST:g} to {FOV_MOST:g} degrees, not {fov:g}"
            )
    return {"position": position, "yaw": yaw, "pitch": pitch, "fov": fov}


def diagonal(scene):
    """The diagonal of the scene's box."""
    positions = np.asarray(scene["positions"], dtype=np.float64)
    return float(np.linalg.norm(positions.max(axis=0) - positions.min(axis=0)))
