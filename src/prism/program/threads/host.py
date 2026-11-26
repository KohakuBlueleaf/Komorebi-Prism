"""The threads' form's host of the frame: each layer's mesh, lists, counts, row
histograms and positions, the records, the capacity of the dispatcher and of the
classes, and the dispatcher's numbers and every view's layer columns written."""

import numpy as np

import prism.stages.raster.host as raster_host  # the module: the packages import in a cycle
from prism.core.capacity import Capacity, capacity, default_capacity, narrow, need
from prism.core.implementation import Host
from prism.program.assemble import MissingSlot
from prism.program.dispatch import thread as dispatch
from prism.stages.material.texture.host import with_table
from prism.stages.raster.model.counts import kept_counts
from prism.stages.raster.model.numbers import PAGE_SLOTS, PAGE_WORDS
from prism.stages.raster.threads import layout
from prism_reference.scene.frame import frame_grid, frame_size

VISIBILITY = "frame.visibility"  # the planes: on the cores, no tensor of the frame
LISTS = "frame.lists"  # each layer's lists by its name (the texture host's rows)
ATTRIBUTES = "mesh.attributes"  # each layer's shade blocks, by its name
DISPLAY = "display.picture"  # the target a COLOUR view's post step writes
CAMERAS = "view.depth"  # another host's DEPTH views: indices, cameras, frame size
DEPTH_LAYERS = raster_host.DEPTH_LAYERS  # the layers a DEPTH view draws
RANGE_BLOCKS = 4  # the triangle blocks a count range holds, unless given
POLICY = "prefer"  # the tile pull's choice, unless given
NEAR = 1  # the slices a near answer may be away, unless given
HEAVY = 0  # the weight past which a tile is cut into bands (0: never), unless given


def band_count(weight, heavy):
    """The bands a tile of `weight` entries over every layer is cut into at most: one
    when `heavy` is 0 or not passed, else ceil(weight / heavy) up to kBandsMost."""
    weight = np.asarray(weight, np.int64)
    if not heavy:
        return np.ones_like(weight)
    bands = np.minimum(-(-weight // int(heavy)), layout.G["kBandsMost"])
    return np.where(weight > heavy, bands, 1)


def slots_needed(scenes, size, heavy):
    """{layer: list slots} the frame of `size` needs for the layers' `scenes` {name:
    scene with its camera}: each tile's entries, again in each band of a cut tile."""
    across, down = frame_grid(size)
    counts = {name: kept_counts(one, across, down) for name, one in scenes.items()}
    weight = sum(counts.values())
    bands = band_count(weight, heavy)
    return {
        name: int((np.asarray(one, np.int64) * bands).sum())
        for name, one in counts.items()
    }


def whole_pages(slots):
    """`slots` list slots up to whole list pages (one page at least)."""
    return max(1, -(-int(slots) // PAGE_SLOTS)) * PAGE_SLOTS


class ThreadsHost(Host):
    """What the threads' frame needs on the host for `scene` on `session`. Options:
    size, cores, capacity (at least it), materials, lights (the layers' blocks as the
    raster stage makes them), range_blocks, policy, near, heavy, list_slots_least
    (a number or a dict by layer name)."""

    threads = True  # the frame's host of the threads' form

    def __init__(self, session, scene, options):
        self.session = session
        self.scene = scene
        self.options = options
        self.cores = options.get("cores") or session.ranks
        self.size = tuple(options.get("size") or frame_size(scene))
        self.at_least = options.get("capacity") or default_capacity()
        self.materials = options.get("materials")
        self.lights = options.get("lights")
        self.range_blocks = int(options.get("range_blocks") or RANGE_BLOCKS)
        self.policy = options.get("policy") or POLICY
        self.near = int(options.get("near", NEAR))
        self.heavy = int(options.get("heavy", HEAVY))
        self.least = options.get("list_slots_least") or 0
        self.layers = {}  # by name: its tensors and numbers
        self.depth_views = ()  # another host's DEPTH views
        self.loaded = None  # the run whose numbers and rows are written
        self.written = None  # the size whose grid is written

    def tensor(self, rows):
        """A row-major uint32 array as a DRAM tensor, a page a row."""
        return self.session.tensor(np.asarray(rows, dtype=np.uint32), "uint32")

    def prepare(self):
        """Each layer's mesh blocks and its lists for the eye's view (grown at
        connect for DEPTH views)."""
        meshes = raster_host.layer_meshes(self.scene, self.materials, self.lights)
        self.scenes = {name: one for name, one, _ in meshes}
        eye = slots_needed(self.scenes, self.size, self.heavy)
        for name, _, blocks in meshes:
            self.layers[name] = {
                "blocks": len(blocks),
                "mesh": self.tensor(blocks),
                "shade": None,
                "slots": 0,
            }
            self.lists_for(name, eye[name])

    def lists_for(self, name, slots):
        """The layer `name`'s lists holding at least `slots` (and its least), made
        again only when they grow."""
        least = raster_host.by_layer(self.least, name, 0)
        slots = whole_pages(max(int(slots), int(least)))
        one = self.layers[name]
        if slots <= one["slots"]:
            return
        pages = slots // PAGE_SLOTS
        one["lists"] = self.tensor(np.zeros((pages, PAGE_WORDS), dtype=np.uint32))
        one["slots"] = slots
        lists = getattr(self, "given_lists", None)
        if lists is not None:
            lists[name].update(directory=one["lists"], lists=one["lists"])

    def slots(self):
        """Each layer's lists (frame.lists: as the texture host takes the raster
        stage's, the lists for both); no frame tensor (frame.visibility empty)."""
        self.given_lists = {
            name: {"directory": one["lists"], "lists": one["lists"]}
            for name, one in self.layers.items()
        }
        return {VISIBILITY: {}, LISTS: self.given_lists}

    def connect(self, assembled):
        """The shade blocks (mesh.attributes), the display (display.picture), the
        DEPTH views (view.depth) when a host gives them; then the capacity and the
        tensors every layer and the records need."""
        attributes = assembled.slot(ATTRIBUTES)
        for name, one in self.layers.items():
            one["shade"] = attributes[name]
        self.display = assembled.slot(DISPLAY)
        sizes = [self.size]
        try:
            views = assembled.slot(CAMERAS)
        except MissingSlot:
            views = None
        if views:
            self.depth_views = tuple(views["views"])
            size = tuple(views["size"])
            sizes.append(size)
            for camera in views["cameras"]:
                scenes = {
                    name: {**self.scenes[name], "camera": camera, "size": size}
                    for name in DEPTH_LAYERS
                    if name in self.scenes
                }
                for name, slots in slots_needed(scenes, size, self.heavy).items():
                    self.lists_for(name, slots)
        held = capacity(sizes, lit=bool(views), at_least=self.at_least)
        held = held._replace(cores=self.cores)
        self.held = with_table(held, self.materials) if self.materials else held
        self.capacity = self.capacity_of(sizes)
        self.made_tensors()

    def capacity_of(self, sizes):
        """The dispatcher's capacity: the count ranges of every layer, the most slices
        of a frame of `sizes`."""
        ranges = sum(
            -(-one["blocks"] // self.range_blocks) for one in self.layers.values()
        )
        slices = max(layout.slices_of(*frame_grid(size)) for size in sizes)
        return dispatch.Capacity(ranges, slices)

    def made_tensors(self):
        """The records (a 64-byte page each), each layer's counts, row histograms and
        positions (a page a core)."""
        cap, tiles = self.capacity, self.held.tiles
        words = layout.RECORD_BYTES // 4
        self.records = self.tensor(
            np.zeros((cap.slices * cap.slice_records, words), dtype=np.uint32)
        )
        pages = layout.layer_pages(tiles, cap.slices, cap.slice_records)
        for one in self.layers.values():
            for name, bytes_ in pages.items():
                one[name] = self.tensor(
                    np.zeros((self.cores, bytes_ // 4), dtype=np.uint32)
                )

    @property
    def tensors(self):
        """{records, display: tensor; lists, counts, rows, positions: [a layer's
        tensor, in layer order]}."""
        out = {"records": self.records, "display": self.display}
        for name in ("lists", "counts", "rows", "positions"):
            out[name] = [one[name] for one in self.layers.values()]
        return out

    def numbers(self):
        """The dispatcher's numbers: the policy, near, heavy, range blocks, the
        records' and the display's addresses."""
        return dispatch.numbers(
            self.policy,
            self.near,
            self.heavy,
            self.range_blocks,
            self.records.address,
            self.display.address,
        )

    def columns(self, name):
        """The layer `name`'s row: the dispatcher's columns, whether a DEPTH view draws
        it."""
        one = self.layers[name]
        row = dispatch.columns(
            one["mesh"].address,
            one["blocks"],
            one["shade"].address,
            one["lists"].address,
            one["slots"],
            one["counts"].address,
            one["rows"].address,
            one["positions"].address,
        )
        return row | {"depth": int(name in DEPTH_LAYERS)}

    def need(self, size):
        """The tiles of a frame of `size`; wide past the narrow grid."""
        return Capacity(need([size]), not narrow(frame_grid(size)))

    def view(self, loaded, camera, size):
        """The dispatcher's numbers (every phase) and every view's layer rows once a
        run; the camera, and the grid and tiles when the size changed."""
        if self.loaded is not loaded:
            loaded.numbers(self.numbers() | {dispatch.PHASES: 0})
            for index, name in enumerate(self.layers):
                loaded.layer(index, **self.columns(name))
            self.loaded, self.written = loaded, None
        loaded.number("camera", camera)
        if tuple(size) != self.written:
            self.size = tuple(size)
            across, down = frame_grid(self.size)
            grid = raster_host.grid_word(self.size)
            loaded.numbers({"grid": grid, "tiles": across * down})
            self.written = self.size
