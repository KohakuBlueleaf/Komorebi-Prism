"""The entries a tile of a scene's pieces' boxes in a grid, made once for a scene, its
camera, its size and the grid, and kept under the cache root."""

import hashlib
import json
import os

import numpy as np

from prism_common.paths import cache_root
from prism_reference.raster.fill import tile_counts
from prism_reference.raster.setup import boxes
from prism_reference.scene.frame import frame_size

VERSION = 1  # of what is kept: another value keys every scene anew
NAME_DIGITS = 16  # of the digest, naming the file
MADE = {}  # by digest: what this process has made or loaded


def digest(scene, across, down):
    """The BLAKE2b hex digest of the version, the positions, the indices, the camera
    (each its dtype, shape and bytes), the frame's size and the grid."""
    hasher = hashlib.blake2b()
    hasher.update(f"{VERSION}".encode())
    for key in ("positions", "indices", "camera"):
        array = np.ascontiguousarray(scene[key])
        hasher.update(f"{array.dtype.str} {array.shape}".encode())
        hasher.update(memoryview(array.reshape(-1)).cast("B"))
    hasher.update(f"{frame_size(scene)} {int(across)} {int(down)}".encode())
    return hasher.hexdigest()


def written(stem, key, counts):
    """`counts` to <stem>.npy, then the key file <stem>.json naming the digest, each
    to a temporary name, then renamed."""
    stem.parent.mkdir(parents=True, exist_ok=True)
    part = stem.with_name(f"{stem.name}.npy.{os.getpid()}.part")
    with open(part, "wb") as out:
        np.save(out, np.ascontiguousarray(counts))
    part.replace(stem.with_name(f"{stem.name}.npy"))
    part = stem.with_name(f"{stem.name}.json.{os.getpid()}.part")
    part.write_text(json.dumps({"digest": key, "version": VERSION}))
    part.replace(stem.with_name(f"{stem.name}.json"))


def loaded(stem, key):
    """The counts kept at `stem` for the digest `key`; None when absent or another
    digest's."""
    path = stem.with_name(f"{stem.name}.json")
    if not path.is_file():
        return None
    if json.loads(path.read_text()).get("digest") != key:
        return None
    return np.load(stem.with_name(f"{stem.name}.npy"))


def kept_counts(scene, across, down):
    """`tile_counts(boxes(scene), across, down)`, made once and kept under the cache
    root's counts/."""
    key = digest(scene, across, down)
    if key not in MADE:
        stem = cache_root() / "counts" / key[:NAME_DIGITS]
        counts = loaded(stem, key)
        if counts is None:
            counts = tile_counts(boxes(scene), across, down)
            written(stem, key, counts)
        MADE[key] = counts
    return MADE[key]
