"""The sun's pass on the host for one scene on one session: the lights at the sun, the
sun region's part of its own (the quadrants' cameras, the map's pages; LIGHT's table
before it is the light host's), the column that names LIGHT's table, the SUN command
sent when the sun moves, and its times."""

import numpy as np

import prism.stages.raster.host as raster_host  # the module: the packages import in a cycle
from prism.core.capacity import Capacity, narrow, need
from prism.core.control import Control
from prism.core.implementation import Host
from prism.program.assemble import MissingSlot
from prism.program.loaded import MICROSECONDS
from prism.stages.direct.light.model.sun import scene_box, shadow_of_pages
from prism.stages.direct.shadow_pcf.model.region import (
    QUADRANT,
    SUN_AT,
    across_of,
    lights_at,
    map_pages,
    quadrant_cameras,
    region_words,
    times_rows,
)
from prism_common.paths import data_root
from prism_reference.direct import lights as reference_lights
from prism_reference.direct.lights import placeholder, shadow_side, sun_angles
from prism_reference.scene.frame import frame_grid

SUN = "sun"  # the unit's region and its command
TIMES = "sun_times"
MAP = "light.shadow_map"  # the light pages, the map their first pages
CAMERAS = "view.depth"  # the DEPTH views: indices, cameras, frame size
PAGE_WORDS = 1024  # a map's page
AZIMUTH = (0.0, 360.0)  # the sun's angles a viewer offers, degrees
ELEVATION = (0.0, 90.0)
TURN = 360.0


class ShadowHost(Host):
    """What the sun's pass needs on the host for `scene` on `session`: the lights (by
    the scene's `name` unless `lights` is given), the sun (option `sun`: azimuth,
    elevation; None: the lights' own)."""

    def __init__(self, session, scene, options):
        self.session = session
        self.scene = scene
        self.name = options.get("name")
        self.lights = options.get("lights")
        self.sun = options.get("sun")
        self.side = options.get("shadow_side")
        self.options = options
        self.loaded = None  # the run whose column is written
        self.pending = False  # the SUN command asked for, not yet done
        self.passes = []  # each SUN command sent: the sun, its code
        self.sent = 0  # SUN commands of the loaded run

    def prepare(self):
        """The lights, the scene's box, the quadrants (the views of its own)."""
        if self.lights is None:
            self.lights = reference_lights.load(self.name, data_root())
        if self.side is not None:
            self.lights = {**self.lights, "shadow_side": np.int32(self.side)}
            self.sun = self.sun or sun_angles(self.lights["sun_direction"])
        self.box = scene_box(self.scene)
        self.views = tuple(range(1, 1 + across_of(self.lights) ** 2))
        self.target = None

    def connect(self, assembled):
        """The map's tensor: the light pages (slot light.shadow_map) when a host gives
        them, else a tensor of the map's own."""
        try:
            self.target = assembled.slot(MAP)
        except MissingSlot:
            pages = np.zeros((map_pages(self.lights), PAGE_WORDS), dtype=np.uint32)
            self.target = self.session.tensor(pages, "uint32")
        if self.target.pages < map_pages(self.lights):
            raise ValueError(
                f"direct.shadow_pcf: a map of side {shadow_side(self.lights)} takes "
                f"{map_pages(self.lights)} pages, the light pages hold {self.target.pages}"
            )

    def moved(self):
        """The lights at the sun now."""
        return lights_at(self.lights, self.box, self.sun)

    def region(self, options=None):
        """The sun region's words now: LIGHT's table's words 0 (the light host's), then
        the sun's words and the quadrants' cameras at the sun."""
        grid = raster_host.grid_word(QUADRANT)
        return region_words(self.moved(), grid, self.target)

    def need(self, size):
        """The tiles of a frame of `size` and of a quadrant of the map."""
        return Capacity(need([size], lit=True), not narrow(frame_grid(size)))

    def slots(self):
        """The DEPTH views (slot view.depth): their view indices, each quadrant's
        camera at the sun now, a quadrant's frame size."""
        cameras = quadrant_cameras(self.moved())
        return {CAMERAS: {"views": self.views, "cameras": cameras, "size": QUADRANT}}

    def view(self, loaded, camera, size):
        """Once a run: the column naming LIGHT's table in every layer row; the SUN
        command asked for when the sun was moved or the lights hold a placeholder map.
        """
        if self.loaded is loaded:
            return
        self.loaded, self.sent = loaded, 0
        table = loaded.thread.regions.address(SUN)[1]
        for index in range(loaded.layout.layers):
            loaded.layer(index, sun_table=table)
        self.pending = self.sun is not None or placeholder(self.lights)

    def sun_now(self):
        """The sun's azimuth and elevation: the set one, else the lights' own."""
        return self.sun or sun_angles(self.lights["sun_direction"])

    def commands(self, loaded):
        """SUN, while asked for and the sun is above the horizon."""
        return [SUN] if self.pending and self.sun_now()[1] > 0 else []

    def served(self, loaded, command, code):
        """A SUN command's code kept; done when 0."""
        self.sent += 1
        self.passes.append({"sun": list(self.sun_now()), "code": code})
        self.pending = code != 0

    def controls(self):
        """The sun's direction (azimuth 0 to 360, elevation 0 to 90 degrees)."""
        azimuth, elevation = self.sun or sun_angles(self.lights["sun_direction"])
        return [
            Control(
                "sun",
                "Sun",
                "direction",
                (azimuth % TURN, elevation),
                limits=(AZIMUTH, ELEVATION),
                unit="degrees",
                help="the sun's azimuth and elevation: its map drawn again",
            )
        ]

    def set(self, loaded, name, value):
        """The sun moved: the region's part of its own rewritten, the SUN command asked
        for (the loop sends it before the next frame, above the horizon), the sun kept
        in the options (LIGHT's table follows it, and a reload)."""
        if name != "sun":
            return f"no control {name!r}"
        if not -90.0 <= value[1] <= 90.0:
            return f"the sun's elevation is -90 to 90 degrees, not {value[1]}"
        self.sun = tuple(value)
        loaded.options["sun"] = self.sun
        loaded.write(SUN, self.region()[SUN_AT // 4 :], SUN_AT)
        self.pending = True
        return None

    def map(self, loaded):
        """The card's shadow map (side, side) float32 1/z from the map's pages."""
        (pages,) = loaded.session.read(self.target, pages=map_pages(self.lights))
        return shadow_of_pages(pages.view(np.uint32).reshape(len(pages), -1))

    def times(self, loaded):
        """The SUN commands' times rows, read after the stop."""
        raw = loaded.region(TIMES)
        return times_rows(raw, len(self.views), self.sent, MICROSECONDS)
