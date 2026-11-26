"""What the texture class needs on the host for a scene: the textures' pages, SHADE's
table, each layer's shade blocks (given as slot mesh.attributes) and profiles, lit each
surface (its two frames, its directory); with the raster stage's layers (slots
frame.lists, frame.visibility), each layer's row of SHADE's words and the frame's
picture."""

import numpy as np

from prism.core import fields
from prism.core.capacity import capacity, default_capacity
from prism.core.implementation import Host
from prism.program.assemble import MissingSlot
from prism.stages.material.texture.model.layers import as_shaded, prepare
from prism.stages.material.texture.model.numbers import SH, SURFACE
from prism.stages.material.texture.model.table import table_needs
from prism.stages.raster import capacity as stage_capacity
from prism.stages.raster.model.frame import decoded
from prism.stages.raster.model.numbers import K
from prism_reference.post.display import to_srgb8
from prism_reference.raster.frames import picture
from prism_reference.scene.frame import frame_grid, frame_size

ATTRIBUTES = "mesh.attributes"
VISIBILITY = "frame.visibility"  # the raster stage's frame tensors, by layer
LISTS = "frame.lists"  # the raster stage's directory and lists, by layer
SURFACE_SLOT = "frame.surface"  # lit: each layer's surface directory, by name
PROFILE_WORDS = SH["kShadeProfBytes"] // 4  # a core's profile page
LAYERS = ("opaque", "masked", "glass")
SURFACES = {"opaque": "opaque", "masked": "opaque", "glass": "glass"}  # lit: written
PAGE_WORDS = 1024  # a frame's page
OPAQUE = 0  # the opaque directory word of a layer not merging
MODES = {  # each layer's kShade* bits: the masked one's when a glass layer follows
    "opaque": 0,
    "masked": 0,
    "masked_merged": SH["kShadeMergedDepth"],
    "glass": SH["kShadeGlass"],
}


def uploaded(scene, materials, lights=None, size=None):
    """What is uploaded once for a shaded frame of `materials` (unlit: as shaded; lit
    with `lights`): mesh and shade blocks of each layer, pages, table of `size` words.
    """
    if lights is None:
        return prepare(scene, as_shaded(materials), size=size)
    return prepare(scene, materials, lights, size)


def with_table(held, materials):
    """The capacity `held` holding the materials table `materials` need (never less
    than it held)."""
    words, rows = table_needs(materials)
    return held._replace(
        table=max(held.table, words), table_rows=max(held.table_rows, rows)
    )


def held_of(options, size):
    """The frame's capacity as the raster stage sizes it: `held` when given, else the
    size's at least the options' capacity, with their recount and cores."""
    if options.get("held") is not None:
        return options["held"]
    at_least = options.get("capacity") or default_capacity()
    held = capacity([size], at_least=at_least)
    return held._replace(
        recount=bool(options.get("recount", False)), cores=options.get("cores")
    )


class TextureHost(Host):
    """The textures, the table, each layer's shade blocks and profiles of `scene` on
    `session`. Options: materials (required), cores, held (the frame's capacity; else
    as the raster stage's from size, capacity, recount), lights (the lit forms: each
    surface's tensors)."""

    pictures = True

    def __init__(self, session, scene, options):
        self.session = session
        self.scene = scene
        self.materials = options["materials"]
        self.lights = options.get("lights")
        self.cores = options.get("cores") or session.ranks
        self.size = tuple(options.get("size") or frame_size(scene))
        held = held_of({**options, "cores": self.cores}, self.size)
        self.held = with_table(held, self.materials)
        self.tensors = {}
        self.layers = {}
        self.examples = {}
        self.order = []  # the raster stage's layers, by its row index
        self.lists = self.frames = None  # its slots, once connected
        self.loaded = None  # the run whose layer rows are written
        self.written_lists = {}  # by layer: the lists' addresses its row holds

    def tensor(self, rows):
        """A row-major uint32 array as a DRAM tensor, a page a row."""
        return self.session.tensor(np.asarray(rows, dtype=np.uint32), "uint32")

    def prepare(self):
        """The textures' pages, the table, and per layer its shade blocks and profiles."""
        size = fields.size("frame_table", self.held)
        prepared = uploaded(self.scene, self.materials, self.lights, size)
        self.tensors = {
            "textures": self.tensor(prepared["pages"]),
            "table": self.tensor(prepared["table"].reshape(1, -1)),
        }
        for name in LAYERS:
            key = "shade_blocks" if name == "opaque" else f"{name}_shade_blocks"
            if key not in prepared:
                continue
            self.layers[name] = {
                "shade": self.tensor(prepared[key]),
                "profile": self.tensor(
                    np.zeros((self.cores, PROFILE_WORDS), dtype=np.uint32)
                ),
            }
        if self.lights is not None:
            for name in {SURFACES[name] for name in self.layers}:
                self.layers[name]["surface"] = self.surface_tensors()
        directory = self.tensor(np.zeros((1, K["kDirBytes"] // 4), dtype=np.uint32))
        self.examples = {
            "directory": self.tensor(
                np.zeros((1, K["kDirBytes"] // 4), dtype=np.uint32)
            ),
            "lists": self.tensor(
                np.zeros((1, K["kInPageBytes"] // 4), dtype=np.uint32)
            ),
            "textures": self.tensors["textures"],
            "table": self.tensors["table"],
            "profile": self.layers["opaque"]["profile"],
            "surface": self.surface("opaque") if self.lights is not None else directory,
        }

    def frame_tensors(self):
        """A frame of the capacity's tiles, five pages each, in tensors of chunk_pages."""
        frame_pages = self.held.tiles * K["kPlanes"]
        chunk = stage_capacity.chunk_pages(frame_pages)
        return [
            self.tensor(
                np.zeros((min(chunk, frame_pages - at), PAGE_WORDS), dtype=np.uint32)
            )
            for at in range(0, frame_pages, chunk)
        ]

    def surface_tensors(self):
        """A surface's two frames and its directory (a page a core: both frames'
        words; LIGHT's words 0)."""
        frames = [self.frame_tensors(), self.frame_tensors()]
        page = np.zeros(K["kDirBytes"] // 4, dtype=np.uint32)
        for frame, at in zip(frames, (K["kDirFrame"], SURFACE["kSurfaceSecond"])):
            page[at] = stage_capacity.chunk_pages(sum(t.pages for t in frame))
            page[at + 1 : at + 1 + len(frame)] = [t.address for t in frame]
        return {"frames": frames, "dir": self.tensor(np.tile(page, (self.cores, 1)))}

    def surface(self, layer):
        """The surface directory lit SHADE of `layer` writes (the masked layer's: the
        opaque one's)."""
        return self.layers[SURFACES[layer]]["surface"]["dir"]

    def slots(self):
        """Each layer's shade blocks by its name, as slot mesh.attributes; lit, each
        layer's surface directory by its name (slot frame.surface: the masked layer's
        the opaque one's; LIGHT's words in it the light stage's to write)."""
        given = {ATTRIBUTES: {name: one["shade"] for name, one in self.layers.items()}}
        if self.lights is not None:
            given[SURFACE_SLOT] = {name: self.surface(name) for name in self.layers}
        return given

    def connect(self, assembled):
        """The raster stage's layers (frame.lists, frame.visibility) when the pipeline
        has a giver; ValueError when its layers are not these."""
        try:
            self.lists = assembled.slot(LISTS)
            self.frames = assembled.slot(VISIBILITY)
        except MissingSlot:
            return
        if set(self.lists) != set(self.layers):
            raise ValueError(
                f"material.texture: the raster stage's layers {', '.join(self.lists)}, "
                f"the materials' {', '.join(self.layers)}"
            )
        self.order = list(self.lists)

    def words(self, layer, directory, lists, opaque=None, merged=False):
        """The class's arguments of `layer`'s SHADE but the grid: its directory and
        lists, the textures, table, its profile, the opaque layer's directory (merging)
        and its mode (`merged`: the masked layer's with the merged 1/z)."""
        mode = MODES["masked_merged" if merged else layer]
        return (
            directory,
            lists,
            self.tensors["textures"],
            self.tensors["table"],
            self.layers[layer]["profile"],
            OPAQUE if opaque is None else opaque.address,
            mode,
        )

    def thread_layer(self, name):
        """The layer `name`'s row of SHADE's words: the raster stage's directory and
        lists, the textures, table, its profile, the opaque layer's directory when it
        merges (lit: the masked layer only; the glass layer's surface is its own), its
        mode (unlit: the masked layer's merged 1/z when a glass layer follows), its
        surface's directory (0: unlit; the unit then gives the camera 0)."""
        given, lit = self.lists[name], self.lights is not None
        merging = name == "masked" or (name == "glass" and not lit)
        opaque = self.lists["opaque"]["directory"] if merging else None
        merged = name == "masked" and "glass" in self.lists and not lit
        words = self.words(name, given["directory"], given["lists"], opaque, merged)
        directory, lists, textures, table, profile, opaque_word, mode = words
        surface = None if self.lights is None else self.surface(name)
        return {
            "shade_directory": directory.address,
            "shade_lists": lists.address,
            "textures": textures.address,
            "shade_table": table.address,
            "shade_profile": profile.address,
            "opaque": opaque_word,
            "mode": mode,
            "shade_surface": 0 if surface is None else surface.address,
        }

    def view(self, loaded, camera, size):
        """Each layer's row once a run (after the raster stage's, the same index), and
        again when the raster stage gave it other lists in the live run."""
        self.size = tuple(size)
        if not self.order:
            return
        if self.loaded is not loaded:
            self.written_lists = {}
        for index, name in enumerate(self.order):
            given = self.lists[name]
            addresses = (given["directory"].address, given["lists"].address)
            if self.written_lists.get(name) == addresses:
                continue
            loaded.layer(index, **self.thread_layer(name))
            self.written_lists[name] = addresses
        self.loaded = loaded

    def picture(self, loaded):
        """The frame's colour planes (the opaque layer's, every layer shaded into them)
        as the 8-bit picture of the frame's size; None without the raster stage."""
        if self.frames is None:
            return None
        words = np.concatenate(
            [
                loaded.session.read(tensor)[0].view(np.uint32).reshape(-1)
                for tensor in self.frames["opaque"]
            ]
        )
        planes = decoded(words, *frame_grid(self.size))
        colour = np.ascontiguousarray(np.moveaxis(planes[1:4], 0, 2))
        return to_srgb8(picture(colour, {"size": self.size}))
