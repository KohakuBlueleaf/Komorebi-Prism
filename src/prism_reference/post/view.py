"""Blender's view transforms (AgX, Filmic, their looks) in the form a scene's
`<stem>.view.npz` holds: a 3 x 3 product, the log2 of each channel on a range, a 3D
table of 16-bit entries by tetrahedral interpolation, then the display's 255 thresholds
(the per-channel tail); without a 3D table, the thresholds alone."""

import json
from pathlib import Path

import numpy as np

from prism_reference.post.tone import CURVE_VIEW
from prism_reference.scene.importers.gltf.sidecar import sidecar_path
from prism_reference.scene.public.table import scene_of, table

F = np.float32
VIEW_SUFFIX = ".view.npz"  # beside the sidecar `<stem>.prism.json`
SIDECAR_SUFFIX = ".prism.json"
NO_TRANSFORM = ("", "Standard")
NO_LOOK = ("", "None")
ENTRY_ONE = 65535  # a 16-bit entry's value 1.0
LOG_BITS = 10  # the log2 table's index: the mantissa's top bits
MANTISSA_BITS = 23
EXPONENT_BIAS = 127
TABLE_WORDS = 256  # the thresholds: word k the bits of the smallest float32 of byte k
# log2(1 + i / 2^LOG_BITS), i = 0 .. 2^LOG_BITS, and its steps
LOG_TABLE = np.log2(1.0 + np.arange((1 << LOG_BITS) + 1) / (1 << LOG_BITS)).astype(F)
LOG_STEPS = (LOG_TABLE[1:] - LOG_TABLE[:-1]).astype(F)


def load_view(path):
    """The view of a `.view.npz`: matrix, low, high (the log2 range), cube (n, n, n, 3)
    uint16 or None, thresholds (256,) uint32, record; and the record (view, look,
    display, blender, notes)."""
    with np.load(path) as f:
        view = {
            "matrix": f["matrix"].astype(F),
            "low": float(f["low"]),
            "high": float(f["high"]),
            "cube": f["cube"] if f["cube"].size else None,
            "thresholds": f["thresholds"].astype(np.uint32),
        }
        record = {k: str(f[k]) for k in ("view", "look", "display", "blender")}
        record["notes"] = [str(n) for n in f["notes"]]
    cube = view["cube"]
    if cube is not None and (cube.dtype != np.uint16 or cube.shape[0] < 2):
        raise ValueError(f"{path}: the cube is n^3 x 3 of uint16, n >= 2")
    if view["thresholds"].shape != (TABLE_WORDS,):
        raise ValueError(f"{path}: {TABLE_WORDS} thresholds expected")
    view["record"] = record
    return view, record


def view_of(sidecar):
    """The view of a sidecar's view transform and the notes: None (the standard
    transfer) when it names none, or names one whose file is not beside it (the one
    `render.view_tables` names, else `<stem>.view.npz`)."""
    sidecar = Path(sidecar)
    render = json.loads(sidecar.read_text()).get("render") or {}
    notes = list(render.get("view_notes") or [])
    transform = render.get("view_transform", "")
    if transform in NO_TRANSFORM and render.get("look", "") in NO_LOOK:
        return None, notes
    stem = sidecar.name[: -len(SIDECAR_SUFFIX)]
    path = sidecar.parent / (render.get("view_tables") or stem + VIEW_SUFFIX)
    if not path.is_file():
        notes.append(
            f"view transform {transform!r}: no tables ({stem}{VIEW_SUFFIX}); the "
            "standard transfer used"
        )
        return None, notes
    view, record = load_view(path)
    return view, notes + record["notes"]


def view_from(path):
    """The view and notes of `path`: a sidecar (`view_of`) or a `.view.npz`."""
    path = Path(path)
    if path.name.endswith(SIDECAR_SUFFIX):
        return view_of(path)
    view, record = load_view(path)
    return view, record["notes"]


def scene_sidecar(name):
    """The sidecar of a scene's (or a view's scene's) source file; None for a scene of
    no file or with no sidecar."""
    source = (table().get(scene_of(name), {}).get("source") or {}).get("file")
    if source is None or not sidecar_path(source).is_file():
        return None
    return sidecar_path(source)


def scene_view(name):
    """The view and notes of a scene (or a view's scene): its source file's sidecar's;
    (None, []) for a scene of no file or with no sidecar."""
    sidecar = scene_sidecar(name)
    return (None, []) if sidecar is None else view_of(sidecar)


def with_view(lights, name):
    """`lights` of the scene `name` with its file's display: the exposure 2 ^ the
    sidecar's `render.exposure` (stops) when it has one; the curve CURVE_VIEW and the
    view under "view" when its sidecar has tables; else `lights` as they are."""
    sidecar = scene_sidecar(name)
    if sidecar is None:
        return lights
    render = json.loads(sidecar.read_text()).get("render") or {}
    if "exposure" in render:
        lights = {**lights, "exposure": float(2.0 ** float(render["exposure"]))}
    view, _ = view_of(sidecar)
    return lights if view is None else {**lights, "curve": CURVE_VIEW, "view": view}


def log2_of(x):
    """log2 of positive normal float32 `x`: the exponent plus LOG_TABLE at the
    mantissa's top LOG_BITS, linear over the rest, in float32."""
    bits = np.ascontiguousarray(x, F).view(np.uint32)
    exponent = ((bits >> MANTISSA_BITS).astype(np.int32) - EXPONENT_BIAS).astype(F)
    mantissa = bits & np.uint32((1 << MANTISSA_BITS) - 1)
    rest = MANTISSA_BITS - LOG_BITS
    index = mantissa >> np.uint32(rest)
    fraction = (mantissa & np.uint32((1 << rest) - 1)).astype(F) * F(2.0**-rest)
    return (LOG_TABLE[index] + fraction * LOG_STEPS[index]) + exponent


def coordinates(view, colour):
    """The cube's coordinates (..., 3) in cells, float32, of linear `colour`: the 3 x 3
    product, clamped to the range, log2, scaled to [0, n - 1]."""
    m = view["matrix"]
    x = np.asarray(colour, F)
    r, g, b = x[..., 0], x[..., 1], x[..., 2]
    y = np.stack([(m[k, 0] * r + m[k, 1] * g) + m[k, 2] * b for k in range(3)], -1)
    low, high = view["low"], view["high"]
    y = np.minimum(np.maximum(y, F(2.0**low)), F(2.0**high))
    cells = view["cube"].shape[0] - 1
    scale = F(cells / (high - low))
    return np.minimum(np.maximum((log2_of(y) - F(low)) * scale, F(0)), F(cells))


def tetrahedral(cube, c):
    """The cube's value (..., 3), float32, at coordinates `c` (cells): the fractions
    sorted a >= b >= c, the corners 000, a, a + b, 111 weighted 1 - a, a - b, b - c, c,
    summed in that order over the 16-bit entries, then scaled to [0, 1]."""
    n = cube.shape[0]
    i = np.minimum(c.astype(np.int64), n - 2)
    f = (c - i.astype(F)).astype(F)
    order = np.argsort(-f, axis=-1, kind="stable")
    sorted_f = np.take_along_axis(f, order, -1)
    unit = np.eye(3, dtype=np.int64)
    step_a, step_b = unit[order[..., 0]], unit[order[..., 1]]
    corners = (i, i + step_a, i + step_a + step_b, i + 1)
    weights = (
        F(1) - sorted_f[..., 0],
        sorted_f[..., 0] - sorted_f[..., 1],
        sorted_f[..., 1] - sorted_f[..., 2],
        sorted_f[..., 2],
    )
    total = None
    for corner, weight in zip(corners, weights, strict=True):
        entry = cube[corner[..., 0], corner[..., 1], corner[..., 2]].astype(F)
        term = weight[..., None] * entry
        total = term if total is None else total + term
    return total * F(1.0 / ENTRY_ONE)


def apply_view(view, colour):
    """The values (..., 3), float32, the thresholds read: the cube's at linear
    `colour`, or the colour itself without a cube."""
    if view["cube"] is None:
        return np.asarray(colour, F)
    return tetrahedral(view["cube"], coordinates(view, colour))


def view8(view, colour):
    """Display bytes (..., 3) of linear `colour` through `view`: each value's byte the
    count of thresholds 1 to 255 at or under it."""
    thresholds = view["thresholds"][1:].view(F)
    values = apply_view(view, colour)
    return np.searchsorted(thresholds, values, side="right").astype(np.uint8)
