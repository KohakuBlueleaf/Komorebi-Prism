"""Runs the one-tile product's records on the card: W_T built by the reference on the
written scene of checks.near_field and on a view, written into a bfp8_b tensor, read
back: the bytes equal the host's encode, the values its decode. One JSON line a case,
exit 1 on a difference."""

import argparse
import json
import sys

import komorebi as km
import numpy as np

from checks.near_field import scene as written
from checks.near_field.one_tile import field_model
from prism.stages.indirect.near_tile.model.build import built
from prism.stages.indirect.near_tile.model.weights import (
    WEIGHT_FORMAT,
    decode,
    encode,
    records,
)
from prism_common.formats import TILE
from prism_common.paths import data_root
from prism_reference.direct.lights import load as load_lights
from prism_reference.indirect.files import load_model
from prism_reference.indirect.near.fuse import near_frame, near_operator
from prism_reference.indirect.near.one_tile import tile_operator
from prism_reference.scene.camera import with_size
from prism_reference.scene.generated import uniform
from prism_reference.scene.public.materials import load_materials
from prism_reference.scene.public.views import make_view


def written_records():
    """The written scene's records (its frame as the march's half frame)."""
    view = written.frame()
    covered, n = view["covered"], view["normal"]
    frame = near_frame(view["camera"], view["point"], n, n, covered, 3)
    op = near_operator(frame, covered, written.SPACING)
    model = field_model(view["point"], covered)
    count = len(model["field_keys"]) * 6
    furnace = (
        np.pi * (0.3 + 0.7 * uniform(np.arange(count), 0, 7))[:, None] * np.ones(3)
    )
    t_op = tile_operator(op, frame, covered, view["point"], n, model, furnace)
    size = (2 * covered.shape[1], 2 * covered.shape[0])
    return records(t_op, size)[0], {"seconds": 0.0}


def view_records(scene, view, size, workers):
    """A view's records at `size` and the build's seconds."""
    data = data_root()
    sized = with_size(make_view(f"{scene}_{view}", data), size)
    materials, _ = load_materials(scene, data)
    lights = load_lights(scene, data)
    out = built(sized, materials, lights, load_model(lights["indirect"]), workers)
    return out["values"], out["seconds"]


def through_card(session, values):
    """`values` written into a bfp8_b tensor and read back: bytes and values equal."""
    tensor = session.empty((len(values), TILE, TILE), WEIGHT_FORMAT.komorebi, "tile")
    tensor.write(values)
    got = np.asarray(tensor.read_bytes()).reshape(len(values), -1)
    want = encode(values)
    back = tensor.read().reshape(values.shape)
    out = {
        "records": len(values),
        "bytes": int(want.size),
        "bytes_equal": bool(np.array_equal(got, want)),
        "values_equal": bool(np.array_equal(back, decode(want))),
        "largest_weight": float(np.abs(values).max()),
    }
    tensor.free()
    return out


def main():
    """The written scene, then the view given."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", default="sponza")
    parser.add_argument("--view", default="overview")
    parser.add_argument("--size", type=int, nargs=2, default=(1920, 1080))
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--card", type=int, default=0)
    args = parser.parse_args()
    cases = {
        "written": written_records,
        f"{args.scene}_{args.view}": lambda: view_records(
            args.scene, args.view, args.size, args.workers
        ),
    }
    built_cases = {name: make() for name, make in cases.items()}
    ok = True
    with km.Session(card=args.card) as session:
        for name, (values, seconds) in built_cases.items():
            out = {"case": name, **through_card(session, values), "build_s": seconds}
            out["ok"] = out["bytes_equal"] and out["values_equal"]
            ok = ok and out["ok"]
            print(json.dumps(out), flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
