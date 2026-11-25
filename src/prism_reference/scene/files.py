"""A scene's files: saving and loading the .npz, the .npy folder, the checksum."""

import hashlib
import os
from pathlib import Path

import numpy as np

KEYS = ("positions", "colors", "indices", "camera", "light", "eps", "meta")


def save_beside(path, save):
    """Calls save(name) for a name of this process's own beside `path`, then moves it
    to `path`, so a reader never sees it half written."""
    path = Path(path)
    temporary = path.with_name(f".{path.stem}-{os.getpid()}{path.suffix}")
    try:
        save(temporary)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def save_scene(path, scene):
    """Saves a scene as an uncompressed .npz (save_beside)."""
    save_beside(path, lambda name: np.savez(name, **scene))


def load_scene(path):
    """Loads a scene saved by `save_scene`."""
    with np.load(path) as data:
        return {key: data[key] for key in KEYS}


def export_npy(scene, folder):
    """Writes each array of a scene as <folder>/<key>.npy, the input of the C++ code."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for key in KEYS:
        save_beside(folder / f"{key}.npy", lambda name, k=key: np.save(name, scene[k]))


def checksum(scene):
    """SHA-256 hex digest over the bytes of every array, in KEYS order."""
    digest = hashlib.sha256()
    for key in KEYS:
        digest.update(np.ascontiguousarray(scene[key]).tobytes())
    return digest.hexdigest()
