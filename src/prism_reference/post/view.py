"""Blender's view transforms (AgX, Filmic, a look) as the operations its OpenColorIO
evaluates from scene linear to display values, read from a scene's `<stem>.view.npz`:
matrices, logarithms, powers, 1D and 3D tables."""

import json
from pathlib import Path

import numpy as np

F = np.float32
VIEW_SUFFIX = ".view.npz"  # beside the sidecar `<stem>.prism.json`
SIDECAR_SUFFIX = ".prism.json"
NO_TRANSFORM = ("", "Standard")
FLT_MIN = F(np.finfo(np.float32).tiny)


def load_view(path):
    """The operations [(kind, {name: array})] of a `.view.npz` and its record (view,
    look, display, blender, notes)."""
    with np.load(path) as f:
        kinds = [str(k) for k in f["kinds"]]
        ops = []
        for i, kind in enumerate(kinds):
            prefix = f"op{i}_"
            numbers = {k[len(prefix) :]: f[k] for k in f.files if k.startswith(prefix)}
            ops.append((kind, numbers))
        record = {k: str(f[k]) for k in ("view", "look", "display", "blender")}
        record["notes"] = [str(n) for n in f["notes"]]
    for kind, _ in ops:
        if kind not in OPERATIONS:
            raise ValueError(f"{path}: the operation {kind!r} is not evaluated")
    return ops, record


def view_of(sidecar):
    """The operations of a sidecar's view transform and the notes: None (the standard
    transfer) when it names none, or names one whose tables are not beside it."""
    sidecar = Path(sidecar)
    render = json.loads(sidecar.read_text()).get("render") or {}
    view = render.get("view_transform", "")
    notes = list(render.get("view_notes") or [])
    if view in NO_TRANSFORM and render.get("look", "") in ("", "None"):
        return None, notes
    name = render.get("view_tables")
    path = sidecar.parent / name if name else None
    if path is None or not path.is_file():
        stem = sidecar.name[: -len(SIDECAR_SUFFIX)]
        notes.append(
            f"view transform {view!r}: no tables ({stem}{VIEW_SUFFIX}); the standard "
            "transfer used"
        )
        return None, notes
    ops, record = load_view(path)
    return ops, notes + record["notes"]


def apply_view(ops, colour):
    """Display values (..., 3), float32, of scene-linear `colour` through `ops`."""
    x = np.asarray(colour, F)
    for kind, numbers in ops:
        x = OPERATIONS[kind](x, numbers)
    return x


def view8(ops, colour):
    """Display bytes (..., 3) of scene-linear `colour` through `ops`."""
    return np.rint(np.clip(apply_view(ops, colour), F(0), F(1)) * F(255)).astype(
        np.uint8
    )


def _matrix(x, n):
    """M x + offset."""
    return (x @ n["matrix"].astype(F).T + n["offset"].astype(F)).astype(F)


def _log(x, n):
    """log_base(max(x, FLT_MIN))."""
    return (np.log2(np.maximum(x, FLT_MIN)) / F(np.log2(n["base"]))).astype(F)


def _antilog(x, n):
    """base^x."""
    return np.power(F(n["base"]), x).astype(F)


def _power(x, n):
    """max(x, 0)^power."""
    return np.power(np.maximum(x, F(0)), n["power"].astype(F)).astype(F)


def _moncurve(n):
    """The break (linear side) and slope of a power with a linear segment."""
    g, o = n["gamma"].astype(np.float64), n["offset"].astype(np.float64)
    encoded_break = o / (g - 1)
    slope = encoded_break / ((encoded_break + o) / (1 + o)) ** g
    return g, o, encoded_break, slope


def _decode(x, n):
    """Encoded to linear: ((x + o) / (1 + o))^g over the break, x / slope under it."""
    g, o, brk, slope = _moncurve(n)
    curve = np.power(np.maximum((x + F(o)) / F(1 + o), F(0)), F(g))
    return np.where(x > F(brk), curve, x / F(slope)).astype(F)


def _encode(x, n):
    """Linear to encoded: (1 + o) x^(1/g) - o over the break, slope x under it."""
    g, o, brk, slope = _moncurve(n)
    curve = F(1 + o) * np.power(np.maximum(x, F(0)), F(1 / g)) - F(o)
    return np.where(x > F(brk / slope), curve, x * F(slope)).astype(F)


def _table(x, n):
    """A 1D table per channel over [0, 1] (clamped), linear between entries."""
    table = n["table"].astype(F)
    last = table.shape[0] - 1
    u = np.clip(x, F(0), F(1)) * F(last)
    i = np.minimum(u.astype(np.int64), last - 1)
    f = u - i.astype(F)
    channels = np.arange(3)
    lo, hi = table[i, channels], table[i + 1, channels]
    return (lo + f * (hi - lo)).astype(F)


def _corners(x, cube):
    """The cell's corner index and fraction of x in a cube over [0, 1]^3 (clamped)."""
    last = cube.shape[0] - 1
    u = np.clip(x, F(0), F(1)) * F(last)
    i = np.minimum(u.astype(np.int64), last - 1)
    return i, (u - i.astype(F)).astype(F)


def _cube_tetrahedral(x, n):
    """A 3D table indexed [r, g, b] by tetrahedral interpolation."""
    cube = n["cube"].astype(F)
    i, f = _corners(x, cube)
    r, g, b = (f[..., k : k + 1] for k in range(3))
    i0, i1, i2 = i[..., 0], i[..., 1], i[..., 2]

    def at(dr, dg, db):
        return cube[i0 + dr, i1 + dg, i2 + db]

    c000, c111 = at(0, 0, 0), at(1, 1, 1)
    out = np.empty(x.shape, F)
    left = np.ones(x.shape[:-1], bool)
    # the six tetrahedra by the order of the fractions; the last takes the rest
    for take, (w0, a, wa, b_, wb, w1) in (
        ((r > g) & (g > b), (1 - r, (1, 0, 0), r - g, (1, 1, 0), g - b, b)),
        ((r > b) & (b >= g), (1 - r, (1, 0, 0), r - b, (1, 0, 1), b - g, g)),
        ((b >= r) & (r > g), (1 - b, (0, 0, 1), b - r, (1, 0, 1), r - g, g)),
        ((b > g) & (g >= r), (1 - b, (0, 0, 1), b - g, (0, 1, 1), g - r, r)),
        ((g >= b) & (b > r), (1 - g, (0, 1, 0), g - b, (0, 1, 1), b - r, r)),
        (None, (1 - g, (0, 1, 0), g - r, (1, 1, 0), r - b, b)),
    ):
        mask = left if take is None else take[..., 0] & left
        corner_a, corner_b = at(*a)[mask], at(*b_)[mask]
        w0, wa, wb, w1 = (w[mask] for w in (w0, wa, wb, w1))
        out[mask] = w0 * c000[mask] + wa * corner_a + wb * corner_b + w1 * c111[mask]
        left = left & ~mask
    return out


def _cube_trilinear(x, n):
    """A 3D table indexed [r, g, b] by trilinear interpolation."""
    cube = n["cube"].astype(F)
    i, f = _corners(x, cube)
    out = np.zeros(x.shape, F)
    for dr in (0, 1):
        for dg in (0, 1):
            for db in (0, 1):
                w = np.ones(x.shape[:-1] + (1,), F)
                for k, d in enumerate((dr, dg, db)):
                    w = w * (f[..., k : k + 1] if d else F(1) - f[..., k : k + 1])
                out += w * cube[i[..., 0] + dr, i[..., 1] + dg, i[..., 2] + db]
    return out


def _range(x, n):
    """scale x + offset, clamped to [low, high]."""
    y = x * F(n["scale"]) + F(n["offset"])
    return np.clip(y, F(n["low"]), F(n["high"])).astype(F)


OPERATIONS = {
    "matrix": _matrix,
    "log": _log,
    "antilog": _antilog,
    "power": _power,
    "decode": _decode,
    "encode": _encode,
    "table": _table,
    "cube_tetrahedral": _cube_tetrahedral,
    "cube_trilinear": _cube_trilinear,
    "range": _range,
}
