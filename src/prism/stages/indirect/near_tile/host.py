"""The one-tile product's host: with the option near_tile, W_T built by the reference
for the camera once it stands, written as its records into a bfp8_b tensor (slot
near.weights); without it, nothing."""

import os

import numpy as np

from prism.stages.indirect.near_tile.model.build import built
from prism.stages.indirect.near_tile.model.weights import RECORD_TILES, WEIGHT_FORMAT
from prism_common.formats import TILE
from prism_common.paths import data_root
from prism_reference.direct.lights import load as load_lights
from prism_reference.indirect.files import load_model
from prism_reference.indirect.near.view import furnace_values
from prism_reference.scene.public.materials import load_materials

OPTION = "near_tile"  # the pipeline's option: the one-tile product on
WORKERS = "near_tile_workers"  # the option: the build's processes (else the CPUs')


class NearTileHost:
    """W_T of the standing camera: built when a camera is asked twice in a row and is
    not the one built, written into the tensor of slot near.weights."""

    def __init__(self, session, scene, options):
        self.session = session
        self.scene = scene
        self.options = options
        self.on = bool(options.get(OPTION, False))
        self.workers = int(options.get(WORKERS) or len(os.sched_getaffinity(0)))
        self.name = options.get("name")
        self.lights = options.get("lights")
        self.materials = options.get("materials")
        self.model = None
        self.furnace = None
        self.tensor = None
        self.last = None  # the camera and size of the last frame asked
        self.standing = None  # the camera and size W_T was built for
        self.seconds = {}

    def prepare(self):
        """With the option: the lights, materials, field and its furnace values."""
        if not self.on:
            return
        if self.lights is None:
            self.lights = load_lights(self.name, data_root())
        if self.materials is None:
            self.materials, _ = load_materials(self.name, data_root())
        self.model = load_model(self.lights["indirect"])
        self.furnace = furnace_values(self.model)

    def slots(self):
        """The records' tensor as near.weights, once built."""
        return {} if self.tensor is None else {"near.weights": self.tensor}

    def view(self, loaded, camera, size):
        """W_T built and written when `camera` at `size` stands (asked again) and is
        not the one built."""
        if not self.on:
            return
        eye = (np.asarray(camera, np.float32).tobytes(), tuple(int(s) for s in size))
        if eye == self.last and eye != self.standing:
            self.build(np.asarray(camera, np.float32), eye[1])
            self.standing = eye
        self.last = eye

    def build(self, camera, size):
        """The records of `camera` at `size` in the tensor (made again at a new size)."""
        scene = {**self.scene, "camera": camera, "size": size}
        out = built(
            scene, self.materials, self.lights, self.model, self.workers, self.furnace
        )
        values = out["values"]
        shape = (len(values) * RECORD_TILES, TILE, TILE)
        if self.tensor is None or tuple(self.tensor.shape) != shape:
            if self.tensor is not None:
                self.tensor.free()
            self.tensor = self.session.empty(shape, WEIGHT_FORMAT.komorebi, "tile")
        self.tensor.write(values.reshape(shape))
        self.seconds = out["seconds"]
