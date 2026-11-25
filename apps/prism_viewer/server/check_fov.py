"""The viewer check's part for the pose's field of view: on the running server the view's
own pose posted at a narrower and a wider field of view, then without one (the one
before is kept), then at its own again; the state's field of view follows; each gives a
picture (a label, no control set, the JPEG, its pose) and what it must be against the
picture as loaded.
"""

from prism_viewer.server.camera import FOV_LEAST, FOV_MOST

FACTORS = {"fov narrower": 2.0 / 3.0, "fov wider": 4.0 / 3.0}


def fovs(own):
    """The fields of view tried around `own`, each within FOV_LEAST and FOV_MOST."""
    return {
        label: max(FOV_LEAST, min(FOV_MOST, own * factor))
        for label, factor in FACTORS.items()
    }


def checked(view_pose, scene_serial, post_pose, shown, frame_of, record):
    """The pictures of `view_pose` at each field of view and at its own again, and what
    each must be ("differs" or "same" as loaded); failures in `record`."""
    fail, pictures, expect = record["failures"], [], {}
    record["fovs"] = {}
    tried = fovs(view_pose["fov"])
    wider = tried["fov wider"]
    tried |= {"fov kept": wider, "fov own again": view_pose["fov"]}
    for label, fov in tried.items():
        pose = dict(view_pose, fov=fov)
        sent = {k: v for k, v in pose.items() if k != "fov" or label != "fov kept"}
        serial = post_pose(sent | {"scene_serial": scene_serial})
        state = shown(lambda s, fov=fov: s["fov"] == fov)
        if not serial or state is None or state["status"] != "running":
            fail.append(f"{label}: the pose at {fov:.2f} degrees not taken")
            continue
        data = frame_of(serial, state["frame"])
        if data is None:
            fail.append(f"{label}: no frame")
        record["fovs"][label] = {"fov": fov, "state_fov": state["fov"]}
        pictures.append((label, {}, data, pose))
        expect[label] = "same" if fov == view_pose["fov"] else "differs"
    return pictures, expect
