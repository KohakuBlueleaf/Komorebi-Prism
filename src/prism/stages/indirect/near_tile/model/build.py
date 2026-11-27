"""W_T of a view built on the host by the reference, as the card's records."""

import time

import numpy as np

from prism.stages.indirect.near_tile.model.weights import (
    encode,
    records,
    upsample_records,
)
from prism_reference.indirect.near.half import upsample_weights
from prism_reference.indirect.near.one_tile import FORM
from prism_reference.indirect.near.view import furnace_values, view_frame, view_operator


def built(scene, materials, lights, model, workers=1, furnace=None, terms=("ambient",)):
    """The records' bytes of `scene` (a scene dict with its camera and size) under the
    field `model`, its frame lit by `terms`: a dict of bytes, values, the upsample's
    weights, the half frame's operator, the frame, seconds."""
    started = time.perf_counter()
    furnace = furnace_values(model) if furnace is None else furnace
    frame = view_frame(scene, materials, lights, terms)
    framed = time.perf_counter()
    t_op, marched = view_operator(frame, model, furnace, workers)
    values = records(t_op["w"], scene["size"])
    cam = np.asarray(frame["camera"], np.float64)
    depth = (frame["position"].astype(np.float64) - cam[0:3]) @ cam[9:12]
    taps = upsample_weights(
        marched["depth"], depth, frame["normal"].astype(np.float64), FORM["tile"]
    )
    return {
        "bytes": encode(values),
        "values": values,
        "upsample": upsample_records(taps, scene["size"]),
        "operator": t_op,
        "marched": marched,
        "frame": frame,
        "seconds": {
            "frame": framed - started,
            "operator": time.perf_counter() - framed,
        },
    }
