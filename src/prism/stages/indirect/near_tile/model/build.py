"""W_T of a view built on the host by the reference, as the card's records."""

import time

from prism.stages.indirect.near_tile.model.weights import encode, records
from prism_reference.indirect.near.view import furnace_values, view_frame, view_operator


def built(scene, materials, lights, model, workers=1, furnace=None):
    """The records' bytes of `scene` (a scene dict with its camera and size) under the
    field `model`: a dict of bytes, values, the half frame's operator, seconds."""
    started = time.perf_counter()
    furnace = furnace_values(model) if furnace is None else furnace
    frame = view_frame(scene, materials, lights)
    framed = time.perf_counter()
    t_op, marched = view_operator(frame, model, furnace, workers)
    values = records(t_op["w"], scene["size"])
    return {
        "bytes": encode(values),
        "values": values,
        "operator": t_op,
        "marched": marched,
        "frame": frame,
        "seconds": {
            "frame": framed - started,
            "operator": time.perf_counter() - framed,
        },
    }
