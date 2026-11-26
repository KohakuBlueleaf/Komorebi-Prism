"""The raster stage's host side for one scene on one session: the capacity, its sizes,
the mesh blocks, the tensors a frame needs and the words and region pages a pass takes.
"""

import math
import re

import numpy as np

from prism.core.capacity import Capacity, capacity, default_capacity, narrow, need
from prism.core.control import Control
from prism.core.headers import defined
from prism.core.implementation import Host
from prism.program.assemble import MissingSlot
from prism.program.director.thread import RUNTIME
from prism.stages.material.texture.model.blocks import layer_blocks
from prism.stages.raster import capacity as stage_capacity
from prism.stages.raster.l1 import l1_check
from prism.stages.raster.model import numbers, records
from prism.stages.raster.model.counts import kept_counts
from prism.stages.raster.model.frame import decoded
from prism_reference.raster.fill import BACKGROUND
from prism_reference.scene.frame import frame_grid, frame_size

K, S = numbers.K, numbers.S
SPROF_WORDS = S["kSProfPageBytes"] // 4  # a core's passes' profile page
PROFILE_WORDS = K["kOutPageBytes"] // 4  # a core's FILL profile page
AREA_WORDS = numbers.AREA_PAGES * numbers.AREA_PAGE // 4  # a camera area (setup.h)
CORE_PAGE_WORDS = numbers.AREA_PAGE // 4  # a core's page of the area
STEPS = 4  # the thread's steps: 1 COUNT, 2 the middle pass, 3 PLACE and SETUP, 4 FILL
LIST_MARGIN = 1.25  # grown lists: the slots a frame needed, and a quarter
SHADE_BLOCK_WORDS = S["kShadeBlockBytes"] // 4  # a mesh block's shade block
ATTRIBUTES = "mesh.attributes"  # the material stage's shade blocks, by layer
VISIBILITY = "frame.visibility"  # each layer's frame tensors, by its name
LISTS = "frame.lists"  # each layer's directory and lists, by its name
DEPTH_LAYERS = ("opaque", "masked")  # the layers a DEPTH view draws
CAMERAS = "view.depth"  # another host's DEPTH views: indices, cameras, frame size
UNIT_CODE = re.compile(r"#define\s+(RASTER_\w+)\s+\(DR_UNIT_CODES \+ (\d+)u\)")
# the unit's codes (thread/raster_unit.h) as the thread returns them
CODES = {
    name: defined(RUNTIME / "director.h")["DR_UNIT_CODES"] + int(offset)
    for name, offset in UNIT_CODE.findall(
        (numbers.THREAD / "raster_unit.h").read_text()
    )
}


def grid_word(size):
    """The frame's grid in grid.h's a8 bits (TX from bit 4, TY from bit 18), bank 0."""
    across, down = frame_grid(size)
    return across << 4 | down << 18


def camera_page(scene):
    """A view's camera: its 16 float32 numbers as words."""
    return np.asarray(scene["camera"], dtype=np.float32).view(np.uint32)


def empty_planes():
    """The empty tile's planes: depth 0, the background colour, triangle -1."""
    values = np.concatenate([[0.0], BACKGROUND, [-1.0]]).astype(np.float32)
    return np.repeat(values.view(np.uint32)[:, None], K["kPlaneWords"], axis=1)


def camera_area(scene, size, ranges):
    """A camera area's words: the view's page (the camera's 16 numbers, the grid word
    at the view's place), then a page a core with its range (first, end) at words 0
    and 1 (the costs COUNT writes after them)."""
    area = np.zeros(AREA_WORDS, dtype=np.uint32)
    area[: S["kCamWords"]] = np.asarray(scene["camera"], dtype=np.float32).view(
        np.uint32
    )
    area[numbers.VIEW_AT // 4 + numbers.VIEW_GRID] = grid_word(size)
    at = CORE_PAGE_WORDS * (1 + np.arange(len(ranges)))
    area[at], area[at + 1] = ranges[:, 0], ranges[:, 1]
    return area


def area_costs(area, cores):
    """The costs COUNT wrote in a camera area's words: 32 words a core."""
    at = CORE_PAGE_WORDS * (1 + np.arange(cores))[:, None] + numbers.AREA_COSTS_AT // 4
    return area[at + np.arange(32)]


def heavy_page(tiles):
    """HIST's heavy page: the tiles' count, then the tiles."""
    page = np.zeros(S["kHeavyBytes"] // 4, dtype=np.uint32)
    page[0] = len(tiles)
    page[1 : 1 + len(tiles)] = tiles
    return page


def layer_meshes(scene, materials, lights=None):
    """(name, scene, mesh blocks) of each layer: without materials the scene's one;
    with, the opaque, masked and glass triangles' (those it has), shaded blocks (with
    `lights`, the lit ones: every corner's u, v and baked visibility)."""
    if materials is None:
        return [("opaque", scene, records.mesh_blocks(scene))]
    layers = layer_blocks(scene, materials, lights)
    return [(name, layer_scene, blocks) for name, layer_scene, blocks, _, _ in layers]


def list_slots_of(entries, items, cores):
    """List slots for `entries` records over `items` items on `cores` fill cores: a
    header an item, an end slot and a page's padding a core, in whole pages."""
    slots = entries + items + cores * (1 + numbers.PAGE_SLOTS)
    return -(-slots // numbers.PAGE_SLOTS) * numbers.PAGE_SLOTS


def by_layer(value, name, default):
    """An option's value for the layer `name`: a dict's by name (else `default`), or
    the value itself for every layer."""
    if isinstance(value, dict):
        return value.get(name, default)
    return default if value is None else value


class RasterHost(Host):
    """What the raster class needs on the host for `scene` on `session`: after
    `prepare()`, the capacity, its sizes, each layer's mesh blocks, list slots and
    tensors by name. Options: size, cores, recount, balance, steps; capacity (at least
    it); list_slots (the opaque layer's, else the scene's guess); list_fraction (the
    guess's part) and list_slots_least, a number or a dict by layer name;
    depth_list_slots_least, a dict by layer name (the DEPTH views' lists); materials (a
    shaded frame's layers); lights (a lit frame's: the corners' baked visibility)."""

    pictures = True

    def __init__(self, session, scene, options):
        self.session = session
        self.scene = scene
        self.cores = options.get("cores") or session.ranks  # every core, unless told
        self.size = tuple(options.get("size") or frame_size(scene))
        self.recount = bool(options.get("recount", False))
        self.list_slots = options.get("list_slots")
        self.list_fraction = options.get("list_fraction", 1.0)
        self.list_least = options.get("list_slots_least", 0)
        self.at_least = options.get("capacity") or default_capacity()
        self.loaded = None  # the run whose numbers and layer row are written
        self.balance = bool(options.get("balance", True))
        self.steps = int(options.get("steps", STEPS))
        self.materials = options.get("materials")
        self.lights = options.get("lights")
        self.shaded = False  # each layer's shade blocks given by the material stage
        self.depth_least = dict(options.get("depth_list_slots_least") or {})
        self.depth = {}  # the DEPTH views' own tensors by layer, once connected
        self.depth_views = ()  # their indices
        self.depth_slots = {}

    def prepare(self):
        """The capacity of the scene's frame (at least the default's, the fill cores
        the host's), its sizes, the mesh blocks and the tensors."""
        held = capacity([self.size], at_least=self.at_least)
        self.held = held._replace(recount=self.recount, cores=self.cores)
        self.heavy, self.band_items = stage_capacity.heavy_capacity(self.held)
        l1_check(self.held, self.size, self.session.l1()[1])
        self.sizes = numbers.sizes(
            self.held.tiles, self.recount, self.heavy, self.band_items
        )
        self.grid = grid_word(self.size)
        meshes = layer_meshes(self.scene, self.materials, self.lights)
        self.blocks = meshes[0][2]
        self.layer_blocks = {name: blocks for name, _, blocks in meshes}
        self.layer_scenes = {name: layer_scene for name, layer_scene, _ in meshes}
        self.layer_slots = {}
        for name, layer_scene, _ in meshes:
            slots = self.list_slots if name == "opaque" else None
            if slots is None:
                slots = self.guessed_slots(layer_scene, name)
            self.layer_slots[name] = max(slots, int(by_layer(self.list_least, name, 0)))
        self.list_slots = self.layer_slots["opaque"]
        self.tensors = self.made_tensors()
        self.layers = {"opaque": self.tensors}
        for name, _, blocks in meshes[1:]:
            self.layers[name] = self.layer_tensors(blocks, self.layer_slots[name])
        self.examples = {
            "mesh": self.tensors["mesh"],
            "counters": self.tensors["counters"],
            "prefixes": self.tensors["slots"],
            "slots": self.tensors["slots"],
            "histograms": self.tensors["histograms"],
            "hprefix": self.tensors["hprefix"],
            "lists": self.tensors["lists"],
            "directory": self.tensors["directory"],
            "frame": self.tensors["frame"][0],
            "profile": self.tensors["profile"],
            "empty_planes": self.tensors["empty_planes"],
            "shade": self.tensors["shade"],
        }

    def guessed_slots(self, scene, name="opaque", size=None):
        """The list slots `scene`'s triangles need in a frame of `size` (the host's at
        the capacity held when None; else that frame's own tiles): their entries, a
        heavy tile's again in each further band, in whole pages (the layer `name`'s
        list_fraction)."""
        across, down = frame_grid(self.size if size is None else size)
        tiles = self.held.tiles if size is None else across * down
        counts = kept_counts(scene, across, down)
        heaviest = np.sort(counts)[-self.heavy :]
        entries = int(counts.sum()) + (numbers.MAX_BANDS - 1) * int(heaviest.sum())
        slots = list_slots_of(entries, tiles + self.band_items, self.cores)
        fraction = float(by_layer(self.list_fraction, name, 1.0))
        pages = -(-int(slots * fraction) // numbers.PAGE_SLOTS)
        return pages * numbers.PAGE_SLOTS

    def tensor(self, rows):
        """A row-major uint32 array as a DRAM tensor, a page a row."""
        return self.session.tensor(np.asarray(rows, dtype=np.uint32), "uint32")

    def view_tensors(self, list_slots):
        """A layer's tensors a view kind holds of its own: lists of `list_slots`, the
        directory."""
        pages = list_slots // numbers.PAGE_SLOTS
        return {
            "lists": self.tensor(
                np.zeros((pages, numbers.PAGE_WORDS), dtype=np.uint32)
            ),
            "directory": self.tensor(
                np.zeros((self.cores, K["kDirBytes"] // 4), dtype=np.uint32)
            ),
        }

    def layer_tensors(self, blocks, list_slots):
        """A layer's own DRAM tensors at the capacity: its mesh, lists, directory,
        frame, profiles and shade blocks (a one-page placeholder until connected)."""
        cores = self.cores
        frame_pages = self.held.tiles * K["kPlanes"]
        chunk = stage_capacity.chunk_pages(frame_pages)
        return {
            "mesh": self.tensor(blocks),
            **self.view_tensors(list_slots),
            "frame": [
                self.tensor(
                    np.zeros(
                        (min(chunk, frame_pages - at), PROFILE_WORDS), dtype=np.uint32
                    )
                )
                for at in range(0, frame_pages, chunk)
            ],
            "profile": self.tensor(np.zeros((cores, SPROF_WORDS), dtype=np.uint32)),
            "fill_profile": self.tensor(
                np.zeros((cores, PROFILE_WORDS), dtype=np.uint32)
            ),
            "shade": self.tensor(np.zeros((1, SHADE_BLOCK_WORDS), dtype=np.uint32)),
        }

    def made_tensors(self):
        """The DRAM tensors a frame needs at the capacity, by name: the opaque layer's
        and those every layer shares."""
        cores, sizes = self.cores, self.sizes
        return {
            **self.layer_tensors(self.blocks, self.list_slots),
            "counters": self.tensor(
                np.zeros((cores, sizes["kCountBytes"] // 4), dtype=np.uint32)
            ),
            "slots": self.tensor(
                np.zeros((cores, sizes["kSlotsBytes"] // 4), dtype=np.uint32)
            ),
            "histograms": self.tensor(
                np.zeros((cores, 16 * self.heavy), dtype=np.uint32)
            ),
            "hprefix": self.tensor(
                np.zeros((cores, sizes["kHprefixPageBytes"] // 4), dtype=np.uint32)
            ),
            "empty_planes": self.tensor(empty_planes()),
        }

    def slots(self):
        """Each layer's frame tensors (frame.visibility) and its directory and lists
        (frame.lists), by its name."""
        return {
            VISIBILITY: {name: one["frame"] for name, one in self.layers.items()},
            LISTS: {
                name: {"directory": one["directory"], "lists": one["lists"]}
                for name, one in self.layers.items()
            },
        }

    def connect(self, assembled):
        """The DEPTH views' own lists and directory when a host gives them (slot
        view.depth); each layer's shade blocks from the material stage (slot
        mesh.attributes, by layer name) when the pipeline has a giver; else the
        placeholders stay."""
        try:
            self.depth_tensors(assembled.slot(CAMERAS))
        except MissingSlot:
            pass
        try:
            attributes = assembled.slot(ATTRIBUTES)
        except MissingSlot:
            return
        for name, tensors in self.layers.items():
            tensors["shade"] = attributes[name]
        self.examples["shade"] = self.tensors["shade"]
        self.shaded = True

    def depth_tensors(self, views):
        """For DEPTH `views` (their indices, cameras and frame size), each depth
        layer's own lists, sized by the most its cameras need (at least the layer's
        depth_list_slots_least), and directory."""
        if not views:
            return
        self.depth_views = tuple(views["views"])
        for name in DEPTH_LAYERS:
            if name not in self.layer_scenes:
                continue
            scene = self.layer_scenes[name]
            size = tuple(views["size"])
            slots = max(
                self.guessed_slots(
                    {**scene, "camera": camera, "size": size}, name, size
                )
                for camera in views["cameras"]
            )
            self.depth_slots[name] = max(slots, int(self.depth_least.get(name, 0)))
            self.depth[name] = self.view_tensors(self.depth_slots[name])

    def frame_words(self, frame=None):
        """The directory's frame words of the frame tensors `frame` (the host's by
        default): pages a tensor, then their addresses."""
        frame = self.tensors["frame"] if frame is None else frame
        words = np.zeros(16, dtype=np.uint32)
        words[0] = stage_capacity.chunk_pages(sum(t.pages for t in frame))
        words[1 : 1 + len(frame)] = [t.address for t in frame]
        return words

    def thread_numbers(self):
        """The unit's numbers: the balance, the steps."""
        return {"balance": int(self.balance), "steps": self.steps}

    def thread_layer(self, name="opaque"):
        """The layer `name`'s row: its tensors' addresses, its mesh's blocks and its
        lists' slots, its shade blocks' (0: not shaded), the frame's pages a tensor,
        whether it takes part in a DEPTH view."""
        tensors = self.layers[name]
        frame = tensors["frame"]
        row = {
            column: tensors[column].address
            for column in ("mesh", "lists", "directory", "profile", "fill_profile")
        }
        row["blocks"] = len(self.layer_blocks[name])
        row["list_slots"] = self.layer_slots[name]
        row["shade"] = tensors["shade"].address if self.shaded else 0
        row["frame_pages"] = int(self.frame_words(frame)[0])
        row["depth"] = int(name in DEPTH_LAYERS)
        row |= {f"frame_{i}": tensor.address for i, tensor in enumerate(frame)}
        return row

    def view_numbers(self):
        """The eye's view: the camera's page, the grid word and its tiles."""
        across, down = frame_grid(self.size)
        return {
            "camera": camera_page(self.scene),
            "grid": self.grid,
            "tiles": across * down,
        }

    def need(self, size):
        """The tiles of a frame of `size` rounded to TILE_ROWS; wide past the narrow
        grid."""
        return Capacity(need([size]), not narrow(frame_grid(size)))

    def depth_row(self, name):
        """The layer `name`'s columns a DEPTH view holds of its own: its lists, their
        slots, its directory."""
        own = self.depth[name]
        return {
            "lists": own["lists"].address,
            "directory": own["directory"].address,
            "list_slots": self.depth_slots[name],
        }

    def view(self, loaded, camera, size):
        """The unit's numbers and layer rows once a run (a DEPTH view's with its own
        lists and directory); the camera, and the grid and tiles when the size changed.
        """
        if self.loaded is not loaded:
            loaded.numbers(self.thread_numbers())
            for index, name in enumerate(self.layers):
                loaded.layer(index, **self.thread_layer(name))
                if name in self.depth:
                    for view in self.depth_views:
                        loaded.layer(index, view, **self.depth_row(name))
            self.loaded, self.written = loaded, None
        loaded.number("camera", camera)
        if tuple(size) != self.written:
            self.size, self.grid = tuple(size), grid_word(size)
            across, down = frame_grid(size)
            loaded.numbers({"grid": self.grid, "tiles": across * down})
            self.written = self.size

    def recover(self, loaded, code):
        """A layer's lists too small: the slots it needed (its times row, after the
        stop) and a quarter for that layer of that view's kind (the eye's, or the
        DEPTH views'), a reload; the grid past the capacity: a reload."""
        if code == CODES["RASTER_BAD_GRID"]:
            return "reload"
        if code != CODES["RASTER_LISTS_SMALL"]:
            return None
        loaded.stop()
        row = loaded.times()[-1]
        index = row["layer"]
        name = list(self.layers)[index]
        slots = math.ceil(row["slots"][index] * LIST_MARGIN)
        if slots >= 1 << numbers.M["RM_BASE_SLOT_BITS"]:
            return None
        if row["view"] in self.depth_views and name in self.depth:
            least = dict(loaded.options.get("depth_list_slots_least") or {})
            least[name] = max(slots, self.depth_slots[name] + 1)
            loaded.options["depth_list_slots_least"] = least
            return "reload"
        least = loaded.options.get("list_slots_least") or {}
        if not isinstance(least, dict):
            least = {layer: least for layer in self.layers}
        least[name] = max(slots, self.layer_slots[name] + 1)
        loaded.options["list_slots_least"] = least
        return "reload"

    def controls(self):
        """The balance: COUNT's and SETUP's ranges by cost, applied live."""
        return [
            Control(
                "balance",
                "Balance ranges by cost",
                "toggle",
                self.balance,
                help="COUNT's and SETUP's block ranges cut by the last frame's costs",
            )
        ]

    def set(self, loaded, name, value):
        """The balance into the thread's number, kept in the options for a reload."""
        if name != "balance":
            return f"no control {name!r}"
        self.balance = value
        loaded.options["balance"] = value
        loaded.numbers({"balance": int(value)})
        return None

    def picture(self, loaded):
        """The frame's five planes (depth, colour, triangle) of the padded frame."""
        words = np.concatenate(
            [
                loaded.session.read(tensor)[0].view(np.uint32).reshape(-1)
                for tensor in self.tensors["frame"]
            ]
        )
        return decoded(words, *frame_grid(self.size))
