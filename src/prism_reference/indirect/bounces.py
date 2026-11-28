"""The number of bounce passes: the lights' when they give one, else the scene's own,
chosen from its transport so that the estimated rest of the converged bounce light is
at most LEFT."""

import numpy as np

from prism_reference.direct.lights import bounce_count
from prism_reference.indirect.hmatrix.apply import apply

F = np.float32
LEFT = 0.05  # the share of the converged bounce light the passes may leave out
LUMINANCE = np.array([0.2126, 0.7152, 0.0722], F)
CHOSEN = "chosen_bounces"  # the model's key of the count chosen for it


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


def bounces_of(lights, model):
    """The lights' `bounces` when given (not None), else the scene's (scene_bounces)."""
    given = lights.get("bounces")
    return scene_bounces(model) if given is None else bounce_count(given)
