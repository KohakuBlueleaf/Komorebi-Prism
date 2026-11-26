"""A scene's files under the data root by kind, what each is called when missing, and
the `counts` record a file of them keeps."""

import json
from pathlib import Path

import numpy as np

# kind: (the name under <data>/public, a file inside it when a folder, the missing's name)
FILES = {
    "mesh": ("{name}.npz", None, "no mesh file"),
    "materials": ("{name}_materials.npz", None, "no materials file"),
    "lighting": ("{name}_lighting.npz", None, "no lighting file"),
    "indirect": ("{name}_indirect.npz", None, "no indirect data"),
    "transport": ("{name}_transport", "blocks.npz", "no transport set"),
}


def scene_file(name, kind, data):
    """The path of scene `name`'s file of `kind` under the data root `data`."""
    return Path(data) / "public" / FILES[kind][0].format(name=name)


def present(name, kind, data):
    """True when scene `name`'s file of `kind` is there (a folder with its file)."""
    path, inside = scene_file(name, kind, data), FILES[kind][1]
    return (path / inside).is_file() if inside else path.is_file()


def missing(kind):
    """What a scene lacking its file of `kind` is said to lack."""
    return FILES[kind][2]


def counts(name, kind, data):
    """The JSON `counts` a scene's npz file of `kind` keeps; None when the file or its
    counts are missing."""
    path = scene_file(name, kind, data)
    if not path.is_file():
        return None
    with np.load(path) as f:
        return json.loads(str(f["counts"])) if "counts" in f.files else None
