"""A public scene's views: its camera from the table and the scene dict of a view."""

import numpy as np

from prism_reference.scene.camera import cross, normalize
from prism_reference.scene.frame import HEIGHT, WIDTH
from prism_reference.scene.public.mesh import load_mesh
from prism_reference.scene.public.table import table, views

EPS_SCALE = 2e-5
NEAR_SCALE = 1e-4


def camera(eye, target, fov_deg, near, shift=(0.0, 0.0)):
    """Camera array (16,) float32 looking from eye at target, square field of view; a
    lens `shift` (x, y) in units of WIDTH moves the principal point by (-x, +y) WIDTH.
    """
    eye, target = np.asarray(eye, np.float64), np.asarray(target, np.float64)
    fwd = normalize(target - eye)
    right = normalize(cross(fwd, np.array([0.0, 1.0, 0.0])))
    up = cross(right, fwd)
    focal = (WIDTH / 2) / np.tan(np.radians(fov_deg) / 2)
    tail = [focal, WIDTH / 2 - shift[0] * WIDTH, HEIGHT / 2 + shift[1] * WIDTH, near]
    return np.concatenate([eye, right, up, fwd, tail]).astype(np.float32)


def make_view(view, data):
    """The scene dict of view `<scene>_<view>`; meta: triangles, vertices, then 0, 0, 0."""
    name, v = views()[view]
    entry = table()[name]
    mesh, _ = load_mesh(name, data)
    p = mesh["positions"].astype(np.float64)
    diag = float(np.sqrt(((p.max(0) - p.min(0)) ** 2).sum()))
    spec = entry["views"][v]
    near = spec.get("near", NEAR_SCALE * diag)
    meta = [len(mesh["indices"]), len(p), 0, 0, 0]
    return {
        **mesh,
        "camera": camera(
            spec["eye"], spec["target"], spec["fov"], near, spec.get("shift", (0, 0))
        ),
        "light": np.array(entry["light"], dtype=np.float32),
        "eps": np.array([EPS_SCALE * diag], dtype=np.float32),
        "meta": np.array(meta, dtype=np.int32),
    }
