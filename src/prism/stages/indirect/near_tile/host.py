"""The one-tile product's host: with the option near_tile, W_T built by the reference
for the camera once it stands, its records in a bfp8_b tensor (slot near.weights), the
upsample's weights and, from the reference's frame lit through the field and the field
as the card holds it, S_T a tile (the operands, bfloat16); the unit's numbers; without
it, nothing."""

import os

import numpy as np

from prism.stages.indirect.near_tile.model.build import built
from prism.stages.indirect.near_tile.model.operand import (
    light_pages,
    operand_raw,
    operands,
)
from prism.stages.indirect.near_tile.model.weights import (
    HALF_TILE,
    RECORD_TILES,
    decode,
    encode,
)
from prism.stages.indirect.near_tile.steps.step import NS
from prism_common.formats import TILE, format_of
from prism_common.paths import data_root
from prism_reference.direct.frame import TERMS
from prism_reference.direct.lights import load as load_lights
from prism_reference.direct.lights import placeholder, shadow_side
from prism_reference.direct.shadow import shadow_map
from prism_reference.indirect.files import load_model
from prism_reference.indirect.light import field_for
from prism_reference.indirect.near.view import furnace_values
from prism_reference.scene.frame import frame_grid, frame_size
from prism_reference.scene.public.materials import load_materials

OPTION = "near_tile"  # the pipeline's option: the one-tile product on
WORKERS = "near_tile_workers"  # the option: the build's processes (else the CPUs')
THREAD = "prism.program.threads.tiles:GI_NEAR"  # the tile thread the option needs
NEAR_TAPS = NS["kNearTaps"]  # the upsample's taps a pixel


def half_word(size):
    """The frame word half: the frame's half columns << 16 | its half rows."""
    return ((int(size[0]) + 1) // 2) << NS["kNearHalfShift"] | (int(size[1]) + 1) // 2


def operand_tiles(s):
    """S_T (tiles, WIDTH, 3) as the operands' bfloat16 tiles (tiles, 32, 32): its rows
    W's columns, columns 0 to 2 the channels, the rest 0."""
    out = np.zeros((len(s), TILE, TILE), np.float32)
    out[:, : s.shape[1], : s.shape[2]] = s
    return out


class NearTileHost:
    """W_T of the standing camera: built when a camera is asked twice in a row and is
    not the one built; its records, operands and upsample weights written into tensors,
    the unit's numbers (their addresses, the frame's half size, on) written each
    frame."""

    def __init__(self, session, scene, options):
        self.session = session
        self.scene = scene
        self.options = options
        self.on = bool(options.get(OPTION, False))
        self.workers = int(options.get(WORKERS) or len(os.sched_getaffinity(0)))
        self.name = options.get("name")
        self.lights = options.get("lights")
        self.materials = options.get("materials")
        self.terms = tuple(options.get("terms") or TERMS)
        self.model = None
        self.furnace = None
        self.values = None  # the field's values as the card holds them (entries, 3)
        self.tensors = {}
        self.last = None  # the camera and size of the last frame asked
        self.standing = None  # the camera and size W_T was built for
        self.seconds = {}
        self.built = None

    def prepare(self):
        """With the option: the lights (at the option bounces, their sun's shadow map
        made for a placeholder), materials, field, its card values and furnace; the
        tensors of the frame's size."""
        if not self.on:
            return
        if self.lights is None:
            self.lights = load_lights(self.name, data_root())
        if self.materials is None:
            self.materials, _ = load_materials(self.name, data_root())
        if "bounces" in self.options:
            self.lights = {**self.lights, "bounces": self.options["bounces"]}
        if placeholder(self.lights) and self.lights["sun_direction"][1] > 0:
            depth, _, _ = shadow_map(
                self.scene,
                self.lights["sun_direction"],
                self.materials,
                shadow_side(self.lights),
            )
            self.lights = {**self.lights, "shadow_map": depth}
        self.model = load_model(self.lights["indirect"])
        self.furnace = furnace_values(self.model)
        _, values = field_for({**self.lights, "indirect_packed": True})
        self.values = values.reshape(-1, 3)
        self.made(tuple(self.options.get("size") or frame_size(self.scene)))

    def composed(self, assembled):
        """Refused when the option and the tile thread disagree (GI_NEAR with it)."""
        has = any(s.name == "near_tile" for s in assembled.tile_thread.steps)
        if has != self.on:
            raise ValueError(
                f"option {OPTION}={self.on} with a tile thread "
                f"{'with' if has else 'without'} the near tile step (option "
                f"tile_thread={THREAD} goes with {OPTION}=True)"
            )

    def slots(self):
        """The records' tensor as near.weights, once built."""
        weights = self.tensors.get("weights")
        return {} if weights is None else {"near.weights": weights}

    def view(self, loaded, camera, size):
        """W_T and E built and written when `camera` at `size` stands (asked again) and
        is not the one built; the unit's numbers: on when they are this camera's."""
        if not self.on:
            return
        eye = (np.asarray(camera, np.float32).tobytes(), tuple(int(s) for s in size))
        if eye == self.last and eye != self.standing:
            self.build(np.asarray(camera, np.float32), eye[1])
            self.standing = eye
        self.last = eye
        on = self.standing is not None and eye == self.standing
        for name in ("weights", "operand", "upsample"):
            tensor = self.tensors.get(name)
            loaded.number(f"near_{name}", 0 if tensor is None else tensor.address)
        loaded.number("near_half", half_word(eye[1]))
        loaded.number("near_on", int(on))

    def build(self, camera, size):
        """The records, the operands and the upsample's weights of `camera` at `size`
        in their tensors."""
        scene = {**self.scene, "camera": camera, "size": size}
        out = built(
            scene,
            self.materials,
            self.lights,
            self.model,
            self.workers,
            self.furnace,
            self.terms,
        )
        raw = encode(out["values"])
        s = operands(
            out["operator"],
            out["frame"]["colour"] * out["frame"]["covered"][..., None],
            self.values,
            self.lights["ambient"],
            size,
        )
        e = light_pages(decode(raw), s)  # the product as the host makes it
        self.made(size)
        self.write("weights", raw)
        self.write("operand", operand_raw(operand_tiles(s)))
        self.write("upsample", out["upsample"])
        self.built = {**out, "s": s, "e": e[:, : 3 * HALF_TILE * HALF_TILE]}
        self.seconds = out["seconds"]

    def made(self, size):
        """The tensors of a frame of `size`: the records, the operands, the upsample's
        weights, zero, made again when the size changes (before a load)."""
        across, down = frame_grid(size)
        tiles = across * down
        shapes = {
            "weights": ((tiles * RECORD_TILES, TILE, TILE), "bfp8_b", "tile"),
            "operand": ((tiles, TILE, TILE), "bf16", "tile"),
            "upsample": ((tiles, NEAR_TAPS * TILE * TILE), "fp32", "row"),
        }
        for name, (shape, format, layout) in shapes.items():
            tensor = self.tensors.get(name)
            if tensor is not None and tuple(tensor.shape) == shape:
                continue
            if tensor is not None:
                tensor.free()
            kind = format_of(format)
            self.tensors[name] = self.session.tensor(
                np.zeros(shape, kind.dtype), kind.komorebi, layout
            )
        self.standing = None

    def write(self, name, data):
        """`data` into tensor `name`'s pages, live (also while a run is loaded)."""
        tensor = self.tensors[name]
        pages = np.ascontiguousarray(data).view(np.uint8).reshape(tensor.pages, -1)
        self.session.write(tensor, pages)
