"""LIGHT's host side for one scene on one session: LIGHT's words in the texture stage's
surface directories (slot frame.surface), the light pages, LIGHT's table and where it
is written, the profile pages, the unit's numbers, and the tone, the terms and the
indirect switch written live."""

import numpy as np

from prism.core.control import Control
from prism.core.implementation import Host
from prism.program.assemble import MissingSlot
from prism.stages.direct.light.model import numbers
from prism.stages.direct.light.model.field import field_of
from prism.stages.direct.light.model.sun import scene_box
from prism.stages.direct.light.model.table import light_table
from prism.stages.direct.light.model.terms import light_pages
from prism.stages.direct.light.unit import FORMS
from prism.stages.direct.shadow_pcf.host import SUN
from prism.stages.direct.shadow_pcf.model.region import lights_at
from prism.stages.material.texture.host import held_of, with_table
from prism.stages.material.texture.model.layers import as_shaded
from prism.stages.raster.model.numbers import K
from prism_common.paths import data_root
from prism_reference.direct import lights as reference_lights
from prism_reference.direct.frame import TERMS
from prism_reference.direct.lights import shadow_side
from prism_reference.material.kinds import TRANSPARENT
from prism_reference.post.tone import CURVE_FILMIC, CURVE_PLAIN
from prism_reference.scene.frame import frame_size

LH, SURFACE = numbers.LH, numbers.SURFACE
DIRECTORY_WORDS = K["kDirBytes"] // 4  # a surface directory page a core
PROFILE_WORDS = LH["kLightProfBytes"] // 4  # a core's profile page
LISTS = "frame.lists"  # the raster stage's layers, by name
SURFACES = "frame.surface"  # each layer's surface directory, by name
SCALE = "light.field_scale"  # the field's scale as its last update left it
DISPLAY = "display.picture"  # the display LIGHT writes with the option light_shows
SHOW_TABLE = "show_table"  # the display stage's thresholds' region
SWITCHED = ("shadow", "lamps", "specular", "background")  # the terms a control turns
EXPOSURE = (1e-3, 1e3)  # the tone's limits: exposure, saturation
SATURATION = (0.0, 4.0)
CURVES = ((CURVE_PLAIN, "plain"), (CURVE_FILMIC, "filmic"))  # the tone curves, named
CURVE_HELP = (
    "of x = exposure x colour: plain x / (1 + x); filmic x (2.51 x + 0.03) / "
    "(x (2.43 x + 0.59) + 0.14), clipped to 0 to 1"
)


def glass_of(materials):
    """Whether `materials` give the frame a glass layer (a transparent kind)."""
    if materials is None:
        return False
    shaded = as_shaded(materials)
    return bool((shaded["kind"][shaded["material"]] == TRANSPARENT).any())


def tone_of(lights):
    """The tone step's numbers of `lights` (saturation 1, curve 0 when absent)."""
    return {
        "exposure": float(lights["exposure"]),
        "saturation": float(lights.get("saturation", 1.0)),
        "curve": int(lights.get("curve", 0)),
    }


def shown_table(loaded):
    """The thresholds' region's address in the regions' bank (its place in the loaded
    layout)."""
    _, _, at, _, _ = loaded.layout.regions[SHOW_TABLE]
    _, address = loaded.thread.regions.address(SHOW_TABLE)
    return address + at


class LightHost(Host):
    """What LIGHT needs on the host for `scene` on `session`: after `prepare()`, the
    light pages, the table's region and a surface's table and profile pages; after
    `connect()`, the texture stage's surfaces.
    Options: raster (a raster host: capacity, cores, directory; else as the raster
    stage sizes the frame, from size, cores, capacity, recount), name (the scene's,
    for its lights when `lights` is not given), materials, terms, tone, sun (azimuth,
    elevation), shadow_side (refused unless the lights' map has it), glass (a second surface sharing the table and pages; else whether the
    materials have a glass layer), light_shows (mover B converts for display),
    update_beside (the field's pages twice: the half LIGHT reads and the half the
    update writes)."""

    def __init__(self, session, scene, options):
        self.session = session
        self.scene = scene
        self.raster = options.get("raster")
        self.options = options
        self.name = options.get("name")
        self.lights = options.get("lights")
        self.materials = options.get("materials")
        self.terms = tuple(options.get("terms") or TERMS)
        self.indirect = "indirect" in self.terms
        self.glass = bool(options.get("glass", glass_of(self.materials)))
        self.shows = bool(options.get("light_shows", False))
        self.display = None  # slot display.picture, with light_shows
        self.order = []  # the raster stage's layers, by its row index
        self.surfaces = {}  # the texture stage's surface directories, by layer
        self.scale = None  # slot light.field_scale, when a host gives it
        self.updates = 0  # the field's updates its table has the scale of
        self.sun = None  # the loop's sun its table was written at
        self.loaded = None  # the run whose table is written
        self.numbered = None  # the run whose numbers are written

    def prepare(self):
        """The lights (with the field for the term indirect), the pages, each
        surface's table and profile pages, and the class's examples."""
        if self.lights is None:
            self.lights = reference_lights.load(self.name, data_root())
        side, held = self.options.get("shadow_side"), shadow_side(self.lights)
        if side is not None and int(side) != held:
            raise ValueError(
                f"direct.light: the light pages hold a shadow map of side {held}, the "
                f"option shadow_side is {side}"
            )
        self.tone = self.options.get("tone") or tone_of(self.lights)
        self.box = scene_box(self.scene)
        if self.raster is not None:
            self.held, self.cores = self.raster.held, self.raster.cores
            directory = self.raster.tensors["directory"]
        else:
            self.cores = self.options.get("cores") or self.session.ranks
            size = tuple(self.options.get("size") or frame_size(self.scene))
            self.held = held_of({**self.options, "cores": self.cores}, size)
            directory = self.tensor(np.zeros((self.cores, DIRECTORY_WORDS)))
        if self.materials is not None:
            self.held = with_table(self.held, self.materials)
        self.field = field_of(self.lights) if self.indirect else None
        if self.field is not None and self.options.get("update_beside"):
            self.field = {**self.field, "halves": 2, "half": 0}
        pages, _ = light_pages(self.lights, self.field)
        self.pages = self.tensor(pages)
        self.own = {"opaque": self.light_tensors()}  # by the surface's first layer
        if self.glass:
            self.own["glass"] = self.light_tensors()
        example = self.tensor(np.zeros((self.cores, DIRECTORY_WORDS)))
        self.examples = {"directory": directory, "glass": example, "surface": example}

    def tensor(self, rows):
        """A row-major uint32 array as a DRAM tensor, a page a row."""
        return self.session.tensor(np.asarray(rows, dtype=np.uint32), "uint32")

    def light_tensors(self):
        """A surface's LIGHT tensors: its table and its profile pages."""
        return {
            "table": self.tensor(self.table()[None, :]),
            "profile": self.tensor(np.zeros((self.cores, PROFILE_WORDS))),
        }

    def light_words(self, loaded):
        """LIGHT's words (its table's, its profile's, the pages' addresses; with
        light_shows the display's, its pages and the thresholds' region's) into each
        core's page of the surfaces' directories, the frames' words as the texture
        stage wrote them."""
        session = loaded.session
        for layer, own in self.own.items():
            directory = self.surfaces[layer]
            words = (
                session.read(directory)[0].view(np.uint32).reshape(directory.pages, -1)
            )
            words = words.copy()
            words[:, SURFACE["kSurfaceLightTable"]] = own["table"].address
            words[:, SURFACE["kSurfaceLightProfile"]] = own["profile"].address
            words[:, SURFACE["kSurfaceLightPages"]] = self.pages.address
            if self.shows:
                words[:, SURFACE["kSurfaceShowDisplay"]] = self.display.address
                words[:, SURFACE["kSurfaceShowTable"]] = shown_table(loaded)
                words[:, SURFACE["kSurfaceShowPages"]] = self.display.pages
            session.write(directory, words.view(np.uint8).reshape(directory.pages, -1))

    def table(self):
        """LIGHT's table words now (the tone, the terms, the indirect switch)."""
        return light_table(
            {**self.lights, **self.tone},
            self.materials,
            self.terms,
            self.field,
            self.indirect,
        )

    def slots(self):
        """The light pages: the shadow map's and the field's pages, one tensor."""
        return {"light.shadow_map": self.pages, "light.field": self.pages}

    def connect(self, assembled):
        """The raster's frame (frame.visibility), whose colour planes LIGHT writes;
        its layers' order (frame.lists) when the pipeline has a giver; the texture
        stage's surfaces (frame.surface, by layer: ValueError without one for each
        surface LIGHT reads); the field's scale (light.field_scale) when a host gives
        it; with light_shows the display (display.picture)."""
        self.frame = assembled.slot("frame.visibility")
        if self.shows:
            self.display = assembled.slot(DISPLAY)
        try:
            self.order = list(assembled.slot(LISTS))
        except MissingSlot:
            self.order = []
        try:
            self.scale = assembled.slot(SCALE)
        except MissingSlot:
            self.scale = None
        try:
            self.surfaces = dict(assembled.slot(SURFACES))
        except MissingSlot:
            self.surfaces = {}
        missing = [layer for layer in self.own if layer not in self.surfaces]
        if missing:
            raise ValueError(
                f"direct.light: no surface of the layers {', '.join(missing)} (slot "
                f"{SURFACES}, the texture stage's lit form)"
            )

    def bind(self, loaded):
        """The run whose sun region the table is written to, and the table; LIGHT's
        words into the surfaces' directories."""
        self.loaded = loaded
        self.light_words(loaded)
        self.write_region()

    def thread_numbers(self):
        """The unit's numbers: the surfaces' directories, 1 + the glass layer's index
        (0: none)."""
        glass = self.glass and "glass" in self.order
        return {
            "light_surface": self.surfaces["opaque"].address,
            "light_glass_surface": self.surfaces["glass"].address if glass else 0,
            "light_glass": 1 + self.order.index("glass") if glass else 0,
        }

    def view(self, loaded, camera, size):
        """The unit's numbers once a run."""
        if self.numbered is loaded:
            return
        loaded.numbers(self.thread_numbers())
        self.numbered = loaded

    def commands(self, loaded):
        """None; the table written again when the loop's sun moved or the field was
        updated since (its scale, units and half of the pages from the update's), for
        the next frame."""
        scaled = self.scale is not None and self.field is not None
        if scaled and self.scale["updates"] != self.updates:
            self.updates = self.scale["updates"]
            half = self.scale.get("half", 0)
            self.field = {**self.field, "scale": self.scale["scale"], "half": half}
            self.write_region()
        elif loaded.options.get("sun") != self.sun:
            self.write_region()
        return []

    def live_table(self, options):
        """LIGHT's table now: the lights at the options' sun, the tone, the terms, the
        indirect switch."""
        moved = lights_at(self.lights, self.box, options.get("sun"))
        return light_table(
            {**moved, **self.tone},
            self.materials,
            self.terms,
            self.field,
            self.indirect,
        )

    def write_region(self, region=None):
        """LIGHT's table now (at the loop's sun) into the run's sun region (when
        loaded), the tone and the terms kept in its options for a reload."""
        layout = None if self.loaded is None else self.loaded.layout
        if layout is None or SUN not in layout.regions:
            return
        options = self.loaded.options
        options["tone"], options["terms"] = dict(self.tone), self.terms
        self.sun = options.get("sun")
        self.loaded.write(SUN, self.live_table(options))

    def controls(self):
        """The tone (exposure, saturation, curve), the terms that switch and, with the
        term indirect, the indirect switch."""
        tone = [
            Control("exposure", "Exposure", "range", self.tone["exposure"], EXPOSURE),
            Control(
                "saturation", "Saturation", "range", self.tone["saturation"], SATURATION
            ),
            Control(
                "curve",
                "Tone curve",
                "choice",
                self.tone["curve"],
                choices=CURVES,
                help=CURVE_HELP,
            ),
        ]
        terms = [
            Control(f"term_{name}", f"Term {name}", "toggle", name in self.terms)
            for name in SWITCHED
            if name in TERMS
        ]
        if self.field is not None:
            terms.append(Control("indirect", "Indirect", "toggle", self.indirect))
        return tone + terms

    def set(self, loaded, name, value):
        """A tone number, a term or the indirect switch into LIGHT's table, for the
        next frame."""
        if name == "indirect" and self.field is not None:
            self.set_indirect(value)
            return None
        if name in self.tone:
            tone = {**self.tone, name: value}
            self.set_tone(tone["exposure"], tone["saturation"], tone["curve"])
            return None
        if name.startswith("term_") and name[5:] in SWITCHED:
            term = name[5:]
            kept = [one for one in self.terms if one != term]
            self.terms = tuple(kept + [term] if value else kept)
            self.write_region()
            return None
        return f"no control {name!r}"

    def set_tone(self, exposure, saturation, curve):
        """The tone step's numbers (exposure > 0, saturation >= 0, curve 0 plain or 1
        filmic) into LIGHT's table, for the next frame."""
        exposure, saturation, curve = float(exposure), float(saturation), int(curve)
        if not (exposure > 0 and saturation >= 0) or curve not in (0, 1):
            raise ValueError("a tone is exposure > 0, saturation >= 0, curve 0 or 1")
        self.tone = {"exposure": exposure, "saturation": saturation, "curve": curve}
        self.write_region()

    def set_indirect(self, on):
        """The indirect switch (a host made with the term indirect), for the next
        frame."""
        if self.field is None:
            raise ValueError("the indirect switch needs the term indirect")
        self.indirect = bool(on)
        self.write_region()

    def words(self, form, table_address, camera_address, bank_grid, glass=None):
        """LIGHT's words of `form` (displayed, linear, glass): the table and camera
        at their addresses in the bank of `bank_grid`; glass: (SHADE's table, the
        glass layer's frame directory)."""
        surface = self.surfaces["opaque"]
        shade_table, glass_directory = 0, surface
        if form == "glass":
            surface = self.surfaces["glass"]
            shade_table, glass_directory = glass
        return (
            self.raster.tensors["directory"],
            table_address,
            shade_table,
            camera_address,
            glass_directory,
            surface,
            bank_grid,
            FORMS[form],
        )
