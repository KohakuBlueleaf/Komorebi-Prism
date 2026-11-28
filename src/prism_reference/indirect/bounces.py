"""The number of bounce passes: the lights' when they give one, else the scene's own,
chosen from its transport so that the estimated rest of the converged bounce light is
at most LEFT."""

import hashlib
import json
import os
from pathlib import Path

import numpy as np

from prism_common.paths import cache_root
from prism_reference.direct.lights import bounce_count
from prism_reference.indirect.hmatrix.apply import apply

F = np.float32
LEFT = 0.05  # the share of the converged bounce light the passes may leave out
LUMINANCE = np.array([0.2126, 0.7152, 0.0722], F)
CHOSEN = "chosen_bounces"  # the model's key of the count chosen for it
FOLDER = "bounces"  # the counts chosen for far fields without one, under the cache root
VERSION = 1  # of a kept count: raised when the choice changes


def rest(powers):
    """The estimated share of the converged sum the series `powers` leaves out: its
    last term times r / (1 - r), r the ratio of its last two terms; None when r >= 1."""
    ratio = powers[-1] / powers[-2]
    if ratio >= 1.0:
        return None
    tail = powers[-1] * ratio / (1.0 - ratio)
    return tail / (sum(powers) + tail)


def scene_bounces(model, left=LEFT):
    """The least passes, from 2, whose estimated rest (`rest`) of the series of every
    real element lit by unit irradiance (E1 = M albedo / pi, E_k = M albedo / pi
    E_(k-1), area-weighted luminance) is at most `left`; kept in the model. ValueError
    when the series does not shrink."""
    if CHOSEN in model:
        return int(model[CHOSEN])
    area = np.where(model["real"], model["area"], F(0))
    reflect = np.where(model["real"][:, None], model["albedo"] * F(1 / np.pi), F(0))
    x, powers = reflect.astype(F), []
    while True:
        e = apply(model["blocks"], model["weights"], x)
        powers.append(float(area @ (e @ LUMINANCE)))
        x = (reflect * e).astype(F)
        if len(powers) < 2:
            continue
        if powers[-2] <= 0.0:
            break  # no bounce light: the passes leave nothing out
        share = rest(powers)
        if share is None:
            raise ValueError(
                f"the bounce light does not shrink: pass {len(powers)} carries "
                f"{powers[-1]:.6g} after {powers[-2]:.6g} (ratio >= 1)"
            )
        if share <= left:
            break
    model[CHOSEN] = len(powers)
    return model[CHOSEN]


def far_field_key(path):
    """The key of the far field in the indirect file `path`: its and its matrix files'
    paths, sizes and modification times, LEFT and VERSION (24 hex)."""
    path = Path(path)
    folder = path.with_name(path.name.replace("_indirect.npz", "_transport"))
    stats = []
    for file in (path, folder / "blocks.npz", folder / "weights.f32"):
        st = file.stat()
        stats.append([str(file.resolve()), st.st_size, st.st_mtime_ns])
    text = json.dumps(stats + [LEFT, VERSION])
    return hashlib.sha256(text.encode()).hexdigest()[:24]


def kept_bounces(path, model):
    """scene_bounces of the far field in the indirect file `path`: the model's own
    count, else the one kept under its key, else chosen and kept."""
    if CHOSEN in model:
        return int(model[CHOSEN])
    kept = cache_root() / FOLDER / f"{far_field_key(path)}.json"
    if kept.exists():
        model[CHOSEN] = int(json.loads(kept.read_text())["bounces"])
        return model[CHOSEN]
    count = scene_bounces(model)
    kept.parent.mkdir(parents=True, exist_ok=True)
    part = kept.with_name(f"{kept.name}.{os.getpid()}.part")
    part.write_text(json.dumps({"bounces": int(count)}))
    part.replace(kept)
    return count


def bounces_of(lights, model):
    """The lights' `bounces` when given (not None), else the scene's (kept_bounces, or
    scene_bounces without the indirect file's path)."""
    given = lights.get("bounces")
    if given is not None:
        return bounce_count(given)
    path = lights.get("indirect")
    return scene_bounces(model) if path is None else kept_bounces(path, model)
