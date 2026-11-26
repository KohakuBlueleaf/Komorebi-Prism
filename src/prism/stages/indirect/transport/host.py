"""The apply's host side for one scene on one session: the set, its sizes, the tensors
and the weights' cache."""

import hashlib
import json
from pathlib import Path

import numpy as np

from prism.core.unit import BESIDE, FRAMES
from prism.stages.indirect.transport.plan.deal import deal
from prism.stages.indirect.transport.plan.emulate import x_tiles
from prism.stages.indirect.transport.plan.set import load
from prism.stages.indirect.transport.plan.sizes import sizes
from prism.stages.indirect.transport.plan.tables import tables
from prism.stages.indirect.transport.plan.weights import encode_weights, weight_pages
from prism.stages.indirect.transport.unit import R
from prism.stages.material.texture.host import held_of
from prism_common.formats import TILE, format_of
from prism_common.paths import cache_root, data_root
from prism_reference.scene.public.table import scene_of

ENCODING = 1  # w's encoding: a cached file of another is made again
SET_KEYED = ("blocks.npz", "weights.f32")  # the files a cached w depends on
ORDER = ("x", "w", "y", "tables", "profile")  # apply's tensor parameters
BLOCK = 8  # weight tiles a block
PROFILE_WORDS = 1024  # a core's profile page
RESULTS = ("ticks", "ticks_sum", "ticks_least", "served", "code")  # the unit's words


def set_folder(scene):
    """A scene's transport set: <data root>/public/<scene>_transport/."""
    return data_root() / "public" / f"{scene}_transport"


def scene_name(scene, options):
    """The scene's name: `scene` when it is one, else the scene of the view the
    option `name` names."""
    return scene if isinstance(scene, str) else scene_of(options["name"])


def weights_file(folder, cores):
    """A set's cached w under <cache root>/apply/: <scene>_<key>.npy, the key of
    SET_KEYED's sizes and modification times, `cores`, ENCODING."""
    folder = Path(folder)
    stats = [(folder / name).stat() for name in SET_KEYED]
    text = json.dumps(
        [[st.st_size, st.st_mtime_ns] for st in stats] + [int(cores), ENCODING]
    )
    key = hashlib.sha256(text.encode()).hexdigest()[:16]
    scene = folder.name.removesuffix("_transport")
    return cache_root() / "apply" / f"{scene}_{key}.npy"


def encoded(s, path):
    """w's bytes: read from `path` when it is there, else made and written there whole
    (a temporary name, then renamed); the scene's files of other keys removed."""
    if path.exists():
        return np.load(path, mmap_mode="r")
    raw = encode_weights(s)
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    with open(part, "wb") as out:
        np.save(out, raw)
    part.replace(path)
    scene = path.name.rsplit("_", 1)[0]
    for stale in path.parent.glob(f"{scene}_*.npy"):
        if stale != path and stale.name.rsplit("_", 1)[0] == scene:
            stale.unlink()
    return raw


class TransportHost:
    """What the apply needs on the host for `scene` (a name, or a view's scene with
        the option `name`) on `session`: after `prepare()`, the set, its tables, its sizes,
        w's bytes, x and the tensors by name. Option `compute`: the compute set of the
        program the class joins (None: its own); with it, the frame's capacity (`held`) from
    the options, as the raster stage's. Option `update_beside`: its unit on the cluster
    beside the frames'."""

    def __init__(self, session, scene, options):
        self.session = session
        self.scene = scene
        self.cores = options.get("cores") or session.ranks  # every core, unless told
        self.block = BLOCK
        self.cluster = BESIDE if options.get("update_beside") else FRAMES
        self.folder = set_folder(scene_name(scene, options))
        self.compute = options.get("compute")  # the program's compute set; None: own
        size = options.get(
            "size"
        )  # the frame's capacity, which the frame form sizes by
        held = {**options, "cores": self.cores}
        self.held = held_of(held, tuple(size)) if self.compute and size else None

    def prepare(self):
        """The set read and dealt to the cores, w encoded or read from the cache, the
        tensors made with x the set's own."""
        self.read()
        self.dealt()
        self.tensors = self.slot_tensors() | self.dealt_tensors()

    def read(self):
        """The set and its x read."""
        self.set = load(self.folder)
        self.x = self.set.vector("x.npy")

    def dealt(self, first=None):
        """The set dealt to the cores (`first`: the deal's ranges, else made): its
        tables, sizes and w's bytes encoded or read from the cache."""
        _, pages = weight_pages(self.set)
        first = deal(self.set, self.cores) if first is None else first
        self.tables = tables(self.set, first, pages - 1)
        self.sizes = sizes(self.set, self.tables)
        self.raw = encoded(self.set, weights_file(self.folder, self.cores))

    def slot_tensors(self):
        """x (bf16 tiles) and y (fp32 tiles)."""
        bf16, fp32 = (format_of(name).komorebi for name in ("bf16", "fp32"))
        return {
            "x": self.session.tensor(x_tiles(self.x), bf16, "tile"),
            "y": self.session.empty((TILE, TILE * self.set.tiles), fp32, "tile"),
        }

    def dealt_tensors(self):
        """w (bfp8_b, tiles stored transposed), the tables, the profile pages."""
        session = self.session
        bfp8, u32 = (format_of(name).komorebi for name in ("bfp8_b", "u32"))
        w = session.empty((len(self.raw), TILE, TILE), bfp8, "tile")
        w.transposed_tiles = True
        session.write(w, np.asarray(self.raw))
        return {
            "w": w,
            "tables": session.tensor(self.tables.words, u32),
            "profile": session.empty((self.cores, PROFILE_WORDS), u32),
        }

    def slots(self):
        """x and y: elements.radiance and elements.irradiance."""
        return {
            "elements.radiance": self.tensors["x"],
            "elements.irradiance": self.tensors["y"],
        }

    def bind(self, loaded):
        """Its unit's number: the group's cores."""
        if loaded.layout is not None:
            loaded.number("transport_cores", self.cores)

    def results(self, loaded):
        """The unit's results region read after the stop: the last command's ticks,
        their sum and least, the commands run, the last code."""
        words = loaded.region("transport_results").view(np.uint32)
        return {name: int(words[R[f"TRANSPORT_R_{name.upper()}"]]) for name in RESULTS}

    def words(self, handler):
        """The command words of `handler`."""
        match handler:
            case "apply":
                return tuple(self.tensors[name] for name in ORDER)
        raise KeyError(f"indirect.transport has no handler {handler!r}")
