"""The opened-scene cases: a second open converts nothing and keeps the name, a changed
sidecar gives another name; the lights with "open" (1 a vertex), then replaced by "bake".
"""

import json
import os
import shutil

import numpy as np

from checks.gltf_scene import scene
from checks.gltf_scene.cases import same
from prism_common.paths import DATA_VARIABLE
from prism_reference.direct.prepare import prepare
from prism_reference.scene.artist.opened import open_scene
from prism_reference.scene.public.lighting import environments, lighting_path
from prism_reference.scene.public.table import public_dir, table

SIDECAR = {"version": 1, "source": {"file": "first"}}


def counts_of(name, data):
    """The visibility a vertex of the scene's lighting file and its counts."""
    with np.load(lighting_path(name, data)) as f:
        return f["visibility"], json.loads(str(f["counts"]))


def seed_environment(source, data):
    """The environment maps of the source data root linked into `data` when present
    (else, or without a source, prepare downloads them)."""
    if source is None:
        return
    folder = public_dir(data) / "downloads"
    for entry in environments().values():
        for f in entry["files"]:
            name = f["url"].rsplit("/", 1)[1]
            kept = public_dir(source) / "downloads" / name
            if kept.is_file() and not (folder / name).exists():
                os.symlink(kept, folder / name)


def opened_cases(folder, source):
    """Opens a written file twice, then with a changed sidecar, then makes its lights
    open and baked, under a data root of its own (`source`: where maps may be)."""
    data = folder / "open_data"
    previous = os.environ.get(DATA_VARIABLE)
    os.environ[DATA_VARIABLE] = str(data)
    try:
        cases(folder, data, source)
    finally:
        if previous is None:
            os.environ.pop(DATA_VARIABLE, None)
        else:
            os.environ[DATA_VARIABLE] = previous
        shutil.rmtree(data, ignore_errors=True)


def cases(folder, data, source):
    """The cases of opened_cases."""
    files = folder / "opened"
    files.mkdir()
    path = files / "scene.glb"
    scene.write(path)
    sidecar = files / "scene.prism.json"
    sidecar.write_text(json.dumps(SIDECAR))
    name, first = open_scene(path, data, workers=1)
    again, second = open_scene(path, data, workers=1)
    same("open: first converts", first["converted"], True)
    same("open: second converts nothing", second["converted"], False)
    same("open: second's name", again, name)
    same("open: name's stem", name.rsplit("_", 1)[0], "opened")
    same("open: in the table", name in table(), True)
    sidecar.write_text(json.dumps(SIDECAR | {"source": {"file": "second"}}))
    changed, third = open_scene(path, data, workers=1)
    same("open: changed sidecar, another name", changed != name, True)
    same("open: changed sidecar converts", third["converted"], True)
    seed_environment(source, data)
    prepare(name, data, workers=1, visibility="open")
    visibility, counts = counts_of(name, data)
    same("lights open: visibility 1 everywhere", visibility, np.ones_like(visibility))
    same("lights open: counted open", counts["visibility"], "open")
    prepare(name, data, workers=1, visibility="bake")
    visibility, counts = counts_of(name, data)
    with np.load(public_dir(data) / f"{name}_visibility.npz") as f:
        baked = f["visibility"]
    same("lights bake: replaced, counted baked", counts["visibility"], "baked")
    same("lights bake: the baked visibility", visibility, baked)
    same("lights bake: some vertex below 1", bool((baked < 1).any()), True)
