"""The sun's pass on the host for one scene on one session: the lights at the sun, the
sun region's part of its own (the quadrants' cameras, the map's pages; LIGHT's table
before it is the light host's), the column that names LIGHT's table, the SUN command
sent when the sun moves, the page of maps (the fitted maps kept beside the frames and
the FIT commands that draw them again), and their times."""

import numpy as np

import prism.stages.raster.host as raster_host  # the module: the packages import in a cycle
from prism.core.capacity import Capacity, narrow, need
from prism.core.control import Control
from prism.core.implementation import Command, Host
from prism.program.assemble import MissingSlot
from prism.program.loaded import MICROSECONDS
from prism.stages.direct.light.model.sun import scene_box, shadow_of_pages
from prism.stages.direct.shadow_pcf.model.fit import Fits
from prism.stages.direct.shadow_pcf.model.maps import (
    levels_bytes,
    levels_of_pages,
    maps_bytes,
    of_pages,
)
from prism.stages.direct.shadow_pcf.model.region import (
    QUADRANT,
    SUN_AT,
    H,
    across_of,
    lights_at,
    map_pages,
    quadrant_cameras,
    region_bytes,
    region_words,
    times_rows,
)
from prism_common.paths import data_root
from prism_reference.direct import lights as reference_lights
from prism_reference.direct.lights import placeholder, shadow_side, sun_angles
from prism_reference.scene.frame import frame_grid

SUN = "sun"  # the unit's region and its command
FIT = "fit"  # the command that draws a fitted map again
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
        self.sent = 0  # SUN and FIT commands of the loaded run
        self.fitted = None  # the fitted maps' and the levels' tensor
        self.swap = 0  # 1 + the half the next SUN swaps in (0: none)

    def prepare(self):
        """The lights, the scene's box, the quadrants (the views of its own)."""
        if self.lights is None:
            self.lights = reference_lights.load(self.name, data_root())
        if self.side is not None:
            self.lights = {**self.lights, "shadow_side": np.int32(self.side)}
            self.sun = self.sun or sun_angles(self.lights["sun_direction"])
        self.box = scene_box(self.scene)
        quadrants = self.quadrants = across_of(self.lights) ** 2
        count = int(self.options.get("cascades", 0))
        side = int(self.options.get("cascade_side", QUADRANT[0]))
        if count and side != QUADRANT[0]:
            raise ValueError(f"direct.shadow_pcf: a fitted map's side is {QUADRANT[0]}")
        self.fits = Fits(
            self.scene,
            count,
            side,
            float(self.options.get("cascade_margin", 0.1)),
            bool(self.options.get("shadow_levels", False)),
            self.options.get("cascade_reach"),
            1 + quadrants,
        )
        self.views = tuple(range(1, 1 + quadrants + count))
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
        pages = self.fits.fit_pages(shadow_side(self.lights))
        if pages:
            self.fitted = self.session.tensor(
                np.zeros((pages, PAGE_WORDS), dtype=np.uint32), "uint32"
            )

    def moved(self):
        """The lights at the sun now."""
        return lights_at(self.lights, self.box, self.sun)

    def places(self):
        """The page of maps' first byte in the sun region, the levels' work bytes' first
        byte and their bytes."""
        maps = region_bytes(self.quadrants)
        levels = maps + maps_bytes(1 + self.fits.count)
        return maps, levels, levels_bytes(self.level_sides())

    def region_bytes(self):
        """The sun region's bytes: to the page of maps, it, the levels' work bytes."""
        _, levels, work = self.places()
        return levels + work

    def region(self, options=None):
        """The sun region's words now: LIGHT's table's words 0 (the light host's), then
        the sun's words and the quadrants' cameras at the sun, then the page of maps
        (no fitted map)."""
        grid = raster_host.grid_word(QUADRANT)
        words = region_words(self.moved(), grid, self.target)
        maps, levels, work = self.places()
        sun = words[SUN_AT // 4 :]
        sun[H["SHADOW_PCF_MAPS_AT"]] = maps
        sun[H["SHADOW_PCF_LEVELS_AT"]] = levels
        sun[H["SHADOW_PCF_LEVELS_BYTES"]] = work
        return np.concatenate([words, self.maps_words()])

    def maps_words(self):
        """The page of maps' words now: both halves the whole map's record at the sun
        and no fitted map."""
        grid = raster_host.grid_word(QUADRANT)
        across, down = frame_grid(QUADRANT)
        return self.fits.words(
            self.moved(), self.target, self.fitted, grid, across * down
        )

    def level_sides(self):
        """The sides of the maps whose levels the unit reduces (none without levels)."""
        if not self.fits.levels:
            return []
        side = shadow_side(self.lights)
        return [side] + ([self.fits.side] if self.fits.count else [])

    def need(self, size):
        """The tiles of a frame of `size` and of a quadrant of the map."""
        return Capacity(need([size], lit=True), not narrow(frame_grid(size)))

    def slots(self):
        """The DEPTH views (slot view.depth): their view indices, each quadrant's
        camera at the sun now and each fitted map's of the scene's camera, a quadrant's
        frame size (a fitted map's)."""
        lights = self.moved()
        cameras = quadrant_cameras(lights)
        if self.fits.count:
            cameras = cameras + self.fits.first_cameras(lights["sun_direction"])
        return {CAMERAS: {"views": self.views, "cameras": cameras, "size": QUADRANT}}

    def view(self, loaded, camera, size):
        """Once a run: the column naming LIGHT's table in every layer row; the SUN
        command asked for when the sun was moved or the lights hold a placeholder map;
        every frame, the fitted maps that no longer hold the eye's slices fitted again
        into the half of the page of maps the frames do not read, their FIT commands
        asked for."""
        if self.loaded is not loaded:
            self.loaded, self.sent = loaded, 0
            table = loaded.thread.regions.address(SUN)[1]
            for index in range(loaded.layout.layers):
                loaded.layer(index, sun_table=table)
            self.pending = self.sun is not None or placeholder(self.lights)
            self.pending = self.pending or self.fits.levels
            self.fits.half, self.fits.asked = 0, []
            self.fits.cameras = [None] * self.fits.count
        if self.pending or not self.fits.count or self.sun_now()[1] <= 0:
            return
        written = self.fits.follow(self.moved(), self.target, self.fitted, camera, size)
        if written is not None:
            loaded.write(SUN, written[1], self.places()[0] + written[0])

    def sun_now(self):
        """The sun's azimuth and elevation: the set one, else the lights' own."""
        return self.sun or sun_angles(self.lights["sun_direction"])

    def commands(self, loaded):
        """SUN, while asked for and the sun is above the horizon (with the half of the
        page of maps it swaps in); else the first FIT a redraw asks for."""
        if self.pending and self.sun_now()[1] > 0:
            return [Command(SUN, (self.swap,))]
        if self.fits.asked and not self.pending:
            return [Command(FIT, self.fits.asked[0])]
        return []

    def served(self, loaded, command, code):
        """A SUN command's code kept, done when 0; a FIT's to the fits."""
        self.sent += 1
        if command == FIT:
            self.passes.append({"fit": list(self.fits.asked[0]), "code": code})
            self.fits.served(code)
            return
        self.passes.append({"sun": list(self.sun_now()), "code": code})
        self.pending = code != 0
        if not self.pending and self.swap:
            self.fits.swapped(self.swap - 1)
            self.swap = 0

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
        maps = self.places()[0]
        loaded.write(SUN, self.region()[SUN_AT // 4 : maps // 4], SUN_AT)
        half, at, words = self.fits.gone(self.moved(), self.target, self.fitted)
        loaded.write(SUN, words, maps + at)
        self.swap = 1 + half
        self.pending = True
        return None

    def map(self, loaded):
        """The card's shadow map (side, side) float32 1/z from the map's pages."""
        (pages,) = loaded.session.read(self.target, pages=map_pages(self.lights))
        return shadow_of_pages(pages.view(np.uint32).reshape(len(pages), -1))

    def fitted_maps(self, loaded):
        """The card's maps of the page of maps' half the frames read: per record (the
        whole map's, then each fitted map's present) its index, camera, map (side,
        side) float32 1/z and its levels (none when it has none)."""
        out = []
        whole = self.map(loaded)
        lights = self.moved()
        out.append({"index": 0, "camera": lights["shadow_camera"], "map": whole})
        fits = self.fits
        side = shadow_side(self.lights)
        for index, (camera, place) in enumerate(zip(fits.cameras, fits.places)):
            if camera is None:
                continue
            first = fits.first_of(side, index, place)
            (pages,) = loaded.session.read(
                self.fitted, first=first, pages=fits.per_map()
            )
            pages = pages.view(np.uint32).reshape(fits.per_map(), -1)
            count = (fits.side // 32) ** 2
            out.append(
                {
                    "index": 1 + index,
                    "camera": camera,
                    "map": of_pages(pages[:count], fits.side),
                    "levels": (
                        levels_of_pages(pages[count:], fits.side) if fits.levels else []
                    ),
                }
            )
        if fits.levels:
            (pages,) = loaded.session.read(self.fitted, pages=fits.first_of(side, 0, 0))
            out[0]["levels"] = levels_of_pages(
                pages.view(np.uint32).reshape(-1, 1024), side
            )
        return out

    def times(self, loaded):
        """The SUN commands' times rows, read after the stop."""
        raw = loaded.region(TIMES)
        return times_rows(raw, len(self.views), self.sent, MICROSECONDS)
