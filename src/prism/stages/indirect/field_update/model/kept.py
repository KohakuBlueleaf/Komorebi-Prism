"""The reference's numbers the check judges by, kept on disk by what they are made of:
made before the card is held (`scripts/run/field.py --reference`) and read by the check,
or made by the check and kept when none is there."""

import hashlib
import json
from pathlib import Path

import numpy as np

from prism.stages.indirect.field_update.model.numbers import F32
from prism.stages.indirect.field_update.model.results import expected
from prism.stages.indirect.transport.host import ENCODING, SET_KEYED
from prism_common.paths import cache_root

FOLDER = "field_expected"  # under the cache root
KEYS = ("sky", "l0", "values", "texels", "scale", "pages")


def stamp(path):
    """A file's path, size and modification time."""
    st = Path(path).stat()
    return [str(path), st.st_size, st.st_mtime_ns]


def key_of(lights, bounces, folder):
    """sha256 (24 hex) of the lights' entries, the field model's file, the bounces and,
    with `folder`, the transport set's SET_KEYED files and ENCODING."""
    h = hashlib.sha256()
    for name in sorted(lights):
        value = lights[name]
        h.update(name.encode())
        if isinstance(value, np.ndarray | np.generic):
            a = np.ascontiguousarray(value)
            h.update(f"{a.dtype}{a.shape}".encode())
            h.update(a.tobytes())
        else:
            h.update(repr(value).encode())
    extra = [stamp(lights["indirect"]), int(bounces)]
    if folder is not None:
        extra += [stamp(Path(folder) / name) for name in SET_KEYED] + [ENCODING]
    h.update(json.dumps(extra).encode())
    return h.hexdigest()[:24]


def kept(lights, model, bounces, folder=None, product=None):
    """expected(lights, model, bounces) with the passes by `product()` (None: float32's
    apply; `folder` the transport set it emulates): read when kept, else made and
    kept (a temporary name, then renamed)."""
    path = cache_root() / FOLDER / f"{key_of(lights, bounces, folder)}.npz"
    if path.exists():
        with np.load(path) as f:
            out = {key: f[key] for key in KEYS}
            out["passes"] = list(f["passes"])
        return out
    if product is None:
        out = expected(lights, model, bounces)
    else:
        out = expected(lights, model, bounces, product())
    passes = np.stack(out["passes"]) if out["passes"] else np.zeros((0, 0, 3), F32)
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    with open(part, "wb") as handle:
        np.savez(handle, passes=passes, **{key: out[key] for key in KEYS})
    part.replace(path)
    return out
