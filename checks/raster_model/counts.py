"""The counts without the setup: `boxes` against `setup`'s boxes, `tile_counts` against
`bin_triangles`' counts, `corners` against its form before the positions' split, and
`kept_counts` made, then loaded."""

import os
import shutil
import tempfile
import time
from pathlib import Path

import numpy as np

from checks.raster_model.compare import asserted, compare
from prism.stages.direct.shadow_pcf.host import CAMERAS, ShadowHost
from prism.stages.raster.model import counts as kept
from prism.stages.raster.model.counts import kept_counts
from prism_common.paths import CACHE_VARIABLE, cache_root
from prism_reference.raster.fill import bin_triangles, tile_counts
from prism_reference.raster.setup import (
    boxes,
    camera_space,
    corners,
    grid,
    setup,
    to_screen,
)
from prism_reference.scene.public.views import make_view

SIZES = ((1024, 1024), (1920, 1080))
EXTRA = 3  # further corner values in the corners case
KEPT = "sponza 1920x1080"  # the view of the kept counts' case


def clip_polygon(corners, near):
    """The polygon (list of 6-vectors x, y, z, colour) of a triangle (3, 6) float32 cut
    at z = near; a crossing edge adds the point from its vertex beyond."""
    out = []
    for k in range(3):
        a, b = corners[k], corners[(k + 1) % 3]
        if a[2] > near:
            out.append(a)
        if (a[2] > near) != (b[2] > near):
            inside, outside = (a, b) if a[2] > near else (b, a)
            t = (near - inside[2]) / (outside[2] - inside[2])
            point = inside + t * (outside - inside)
            point[2] = near
            out.append(point.astype(np.float32))
    return out


def corners_before(scene, extra=None):
    """`corners` as it was before the positions' part was a function of its own."""
    cam, idx = scene["camera"], scene["indices"]
    xc, yc, zc = camera_space(scene)
    beyond = (zc > cam[15])[idx].sum(axis=1)
    whole = np.nonzero(beyond == 3)[0]
    pos = np.stack([xc, yc, zc], axis=1)
    pieces, src = [pos[idx[whole]]], [whole]
    values = scene["colors"][idx]
    if extra is not None:
        values = np.concatenate([values, extra.astype(np.float32)], axis=2)
    cols = [values[whole]]
    for t in np.nonzero((beyond == 1) | (beyond == 2))[0]:
        tri = np.concatenate([pos[idx[t]], values[t]], axis=1)
        poly = clip_polygon(tri, cam[15])
        for fan in ([0, 1, 2], [0, 2, 3])[: len(poly) - 2]:
            piece = np.stack([poly[i] for i in fan])
            pieces.append(piece[None, :, :3])
            cols.append(piece[None, :, 3:])
            src.append([t])
    pos, col, src = np.concatenate(pieces), np.concatenate(cols), np.concatenate(src)
    order = np.argsort(src, kind="stable")
    pos, col, src = pos[order], col[order], src[order]
    x, y, w = to_screen(cam, pos[..., 0], pos[..., 1], pos[..., 2])
    return x, y, w, col, src.astype(np.int64)


def depth_views(scene):
    """Sponza under each DEPTH camera the shadow host gives, at its quadrant's size."""
    host = ShadowHost(None, scene, {"name": "sponza"})
    host.prepare()
    views = host.slots()[CAMERAS]
    size = tuple(views["size"])
    return [{**scene, "camera": c, "size": size} for c in views["cameras"]]


def counted_views(data, scenes):
    """(name, scene) of every case: `scenes`, Sponza's overview at SIZES and under each
    DEPTH camera."""
    sponza = make_view("sponza_overview", data)
    views = list(scenes)
    views += [(f"sponza {w}x{h}", {**sponza, "size": (w, h)}) for w, h in SIZES]
    for k, view in enumerate(depth_views(sponza)):
        views.append((f"sponza depth view {k + 1}", view))
    return views


def counts_case(name, scene):
    """`boxes` equal to `setup`'s boxes, `tile_counts` to `bin_triangles`' counts."""
    started = time.perf_counter()
    records = setup(scene)
    across, down = grid(scene)
    got = boxes(scene)
    counts = tile_counts(got, across, down)
    want = bin_triangles(records, across, down)[0]
    seconds = time.perf_counter() - started
    compare(
        f"{name}: boxes and tile_counts without the setup",
        {"box": got, "counts": counts},
        {"box": records["box"], "counts": want},
        seconds,
    )


def corners_case(name, scene):
    """`corners` with and without extra values equal to its form before the split."""
    started = time.perf_counter()
    rng = np.random.default_rng(7)
    extra = rng.random((len(scene["indices"]), 3, EXTRA), dtype=np.float32)
    ours = {"plain": corners(scene), "extra": corners(scene, extra)}
    theirs = {"plain": corners_before(scene), "extra": corners_before(scene, extra)}
    seconds = time.perf_counter() - started
    compare(f"{name}: corners after the split", ours, theirs, seconds)


def near_cut(scene):
    """`scene` with its eye moved into the scene along its forward axis, so the near
    plane cuts triangles."""
    camera = np.array(scene["camera"], dtype=np.float32)
    span = np.ptp(scene["positions"], axis=0).max()
    camera[0:3] += camera[9:12] * np.float32(0.3 * span)
    return {**scene, "camera": camera}


def kept_case(name, scene):
    """`kept_counts` twice (the second loaded from the cache root, the process's dict
    emptied) equal to `tile_counts(boxes(...))`; another camera another key and file."""
    started = time.perf_counter()
    folder = Path(tempfile.mkdtemp(prefix="kept_counts_", dir=cache_root()))
    previous = os.environ.get(CACHE_VARIABLE)
    os.environ[CACHE_VARIABLE] = str(folder)
    try:
        across, down = grid(scene)
        want = tile_counts(boxes(scene), across, down)
        kept.MADE.clear()
        first = kept_counts(scene, across, down)
        kept.MADE.clear()
        key = kept.digest(scene, across, down)
        found = kept.loaded(folder / "counts" / key[: kept.NAME_DIGITS], key)
        second = kept_counts(scene, across, down)
        other = near_cut(scene)
        other_key = kept.digest(other, across, down)
        other_counts = kept_counts(other, across, down)
        files = sorted(p.name for p in (folder / "counts").iterdir())
        compare(
            f"{name}: kept_counts made, then loaded",
            {"first": first, "second": second, "found": found},
            {"first": want, "second": want, "found": want},
            time.perf_counter() - started,
        )
        names = {key[: kept.NAME_DIGITS], other_key[: kept.NAME_DIGITS]}
        want_other = tile_counts(boxes(other), across, down)
        asserted(
            f"{name}: kept_counts of another camera",
            [
                ("another key", key != other_key),
                ("another file", {f"{n}.npy" for n in names} <= set(files)),
                ("its counts", np.array_equal(other_counts, want_other)),
                ("not the first's", not np.array_equal(other_counts, want)),
            ],
            started,
        )
    finally:
        if previous is None:
            os.environ.pop(CACHE_VARIABLE, None)
        else:
            os.environ[CACHE_VARIABLE] = previous
        kept.MADE.clear()
        shutil.rmtree(folder, ignore_errors=True)


def counts_cases(data, scenes):
    """Every counts case and the corners cases (each view; each eye's view moved in
    so the near plane cuts), then the kept counts' case."""
    views = counted_views(data, scenes)
    for name, scene in views:
        counts_case(name, scene)
        corners_case(name, scene)
        if "depth" not in name:
            corners_case(f"{name} moved in", near_cut(scene))
    kept_case(KEPT, dict(views)[KEPT])
