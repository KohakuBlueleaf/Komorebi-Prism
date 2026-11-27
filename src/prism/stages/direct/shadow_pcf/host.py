"""The sun's pass on the host for one scene on one session: the lights at the sun, the
sun region's part of its own (the quadrants' cameras, the map's pages; LIGHT's table
before it is the light host's), the column that names LIGHT's table, the SUN command
sent when the sun moves, the page of maps (the fitted maps kept beside the frames and
the FIT commands that draw them again; the lamps' faces and the LAMPS commands that draw
them), and their times."""

import time

import numpy as np

import prism.stages.raster.host as raster_host  # the module: the packages import in a cycle
from prism.core.capacity import Capacity, narrow, need
from prism.core.control import Control
from prism.core.implementation import Command, Host
from prism.program.assemble import MissingSlot
from prism.program.loaded import MICROSECONDS
from prism.stages.direct.light.model.sun import scene_box, shadow_of_pages
from prism.stages.direct.shadow_pcf.model.faces import Faces
from prism.stages.direct.shadow_pcf.model.fit import Fits
from prism.stages.direct.shadow_pcf.model.maps import (
    SLOT_BYTES,
    TOP_BYTES,
    coarse_pages,
    levels_bytes,
    levels_of,
    maps_bytes,
    of_pages,
)
from prism.stages.direct.shadow_pcf.model.maps import (
    map_pages as pages_of,
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
from prism_reference.direct.lights import shadow_side, sun_angles
from prism_reference.scene.frame import frame_grid

SUN = "sun"  # the unit's region and its command
FIT = "fit"  # the command that draws a fitted map again
LAMPS = "lamps"  # the command that draws lamp faces not drawn
TIMES = "sun_times"
MAP = "light.shadow_map"  # the light pages, the map their first pages
CAMERAS = "view.depth"  # the DEPTH views: indices, cameras, frame size
LAMP_FACES = "light.lamp_faces"  # each lamp's first face record and faces
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
        self.fitted = {}  # the tensors: fitted maps and coarse levels, slots, tops
        self.swap = 0  # 1 + the half the next SUN swaps in (0: none)
        self.lamps_began = 0.0  # when the LAMPS command asked was asked for

    def prepare(self):
        """The lights, the scene's box, the views of its own: the quadrants, the fitted
        maps, the lamps' faces (option `lamp_maps`, default true)."""
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
            float(self.options.get("cascade_margin", 0.25)),
            bool(self.options.get("shadow_levels", False)),
            self.options.get("cascade_reach"),
            1 + quadrants,
            grid_of(QUADRANT),
        )
        self.faces = Faces(
            self.lights if self.options.get("lamp_maps", True) else {},
            self.fits.levels,
            1 + quadrants + count,
            1 + count,
        )
        faces = len(self.faces.faces)
        self.views = tuple(range(1, 1 + quadrants + count + faces))
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
        side = shadow_side(self.lights)
        pages = self.fits.fit_pages(side)
        slots = self.fits.slot_count(side)
        self.faces.place(pages, slots)
        pages += self.faces.pages()
        slots += self.faces.slots()
        if pages:
            self.fitted["maps"] = self.own(pages, PAGE_WORDS)
        if slots:
            self.fitted["slots"] = self.own(slots, SLOT_BYTES // 4)
            self.fitted["tops"] = self.own(slots, TOP_BYTES // 4)
        self.fits.tail = self.faces.records(self.fitted, grid_of)

    def own(self, pages, words):
        """A tensor of its own: `pages` pages of `words` words, refused when its pages
        are aligned to other bytes."""
        tensor = self.session.tensor(
            np.zeros((pages, words), dtype=np.uint32), "uint32"
        )
        if tensor.aligned_page_bytes != 4 * words:
            raise ValueError(
                f"direct.shadow_pcf: a page of {4 * words} B is aligned to "
                f"{tensor.aligned_page_bytes} B"
            )
        return tensor

    def moved(self):
        """The lights at the sun now."""
        return lights_at(self.lights, self.box, self.sun)

    def places(self):
        """The page of maps' first byte in the sun region, the levels' work bytes' first
        byte and their bytes."""
        maps = region_bytes(self.quadrants)
        records = 1 + self.fits.count + len(self.faces.faces)
        levels = maps + maps_bytes(records)
        return maps, levels, levels_bytes(self.level_sizes())

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
        """The page of maps' words now: both halves the whole map's record at the sun,
        no fitted map and the lamps' faces."""
        return self.fits.words(self.moved(), self.target, self.fitted)

    def level_sizes(self):
        """The (width, height) of the maps whose levels the unit reduces (none without
        levels)."""
        if not self.fits.levels:
            return []
        side = shadow_side(self.lights)
        fitted = [(self.fits.side, self.fits.side)] if self.fits.count else []
        return [(side, side)] + fitted + self.faces.sizes()

    def row_views(self):
        """The views a times row holds: the most a command draws."""
        return max(self.quadrants, 1, len(self.faces.faces))

    def need(self, size):
        """The tiles of a frame of `size` and of a quadrant of the map."""
        return Capacity(need([size], lit=True), not narrow(frame_grid(size)))

    def slots(self):
        """The DEPTH views (slot view.depth): their view indices, each quadrant's
        camera at the sun now, each fitted map's of the scene's camera and each lamp
        face's, a quadrant's frame size (no fitted map or face is larger); each lamp's
        first face record and faces (slot light.lamp_faces)."""
        lights = self.moved()
        cameras = quadrant_cameras(lights)
        if self.fits.count:
            cameras = cameras + self.fits.first_cameras(lights["sun_direction"])
        cameras = cameras + self.faces.cameras()
        lamps = self.faces.lamps(len(self.lights["lamp_intensity"]))
        return {
            CAMERAS: {"views": self.views, "cameras": cameras, "size": QUADRANT},
            LAMP_FACES: lamps,
        }

    def view(self, loaded, camera, size):
        """Once a run: the column naming LIGHT's table in every layer row; the SUN
        command asked for (the card draws the map at every load, whatever map the
        lights' file holds); every lamp face not drawn; every frame, the fitted maps
        that no longer hold the eye's slices fitted again into the half of the page of
        maps the frames do not read, their FIT commands asked for."""
        if self.loaded is not loaded:
            self.loaded, self.sent = loaded, 0
            table = loaded.thread.regions.address(SUN)[1]
            for index in range(loaded.layout.layers):
                loaded.layer(index, sun_table=table)
            self.pending = True
            self.fits.half, self.fits.asked = 0, []
            self.fits.cameras = [None] * self.fits.count
            self.faces.restart()
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
        page of maps it swaps in); else the first FIT a redraw asks for and LAMPS while
        a lamp face is not drawn."""
        if self.pending and self.sun_now()[1] > 0:
            return [Command(SUN, (self.swap,))]
        out = []
        if self.fits.asked and not self.pending:
            out.append(Command(FIT, self.fits.asked[0]))
        lamps = self.faces.command()
        if lamps is not None:
            self.lamps_began = time.perf_counter()
            out.append(Command(LAMPS, lamps))
        return out

    def served(self, loaded, command, code):
        """A SUN command's code kept, done when 0; a FIT's to the fits; a LAMPS's to
        the faces with the seconds it took."""
        self.sent += 1
        if command == LAMPS:
            seconds = time.perf_counter() - self.lamps_began
            asked = list(self.faces.asked or ())
            self.passes.append({"lamps": asked, "code": code, "s": round(seconds, 4)})
            self.faces.served(code, seconds)
            return
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

    def read(self, loaded, name, first, pages):
        """`pages` pages of the tensor `name` from page `first` as words (pages, -1)."""
        (out,) = loaded.session.read(self.fitted[name], first=first, pages=pages)
        return out.view(np.uint32).reshape(pages, -1)

    def fitted_maps(self, loaded):
        """The card's maps of the page of maps' half the frames read: per record (the
        whole map's, then each fitted map's present) its index, camera, map (side,
        side) float32 1/z and its levels (none when it has none)."""
        fits = self.fits
        side = shadow_side(self.lights)
        lights = self.moved()
        out = [{"index": 0, "camera": lights["shadow_camera"], "map": self.map(loaded)}]
        if fits.levels:
            slots = self.read(loaded, "slots", 0, pages_of(side))
            coarse = self.read(
                loaded, "maps", fits.coarse_first(side), coarse_pages(side)
            )
            out[0]["levels"] = levels_of(slots, coarse, side)
        for index, (camera, place) in enumerate(zip(fits.cameras, fits.places)):
            if camera is None:
                continue
            count = pages_of(fits.side)
            one = {
                "index": 1 + index,
                "camera": camera,
                "map": of_pages(
                    self.read(loaded, "maps", fits.first_of(index, place), count),
                    fits.side,
                ),
            }
            if fits.levels:
                slots = self.read(
                    loaded, "slots", fits.slot_first(side, index, place), count
                )
                coarse = self.read(
                    loaded,
                    "maps",
                    fits.coarse_first(side, index, place),
                    coarse_pages(fits.side),
                )
                one["levels"] = levels_of(slots, coarse, fits.side)
            out.append(one)
        return out

    def lamp_maps(self, loaded):
        """The card's lamp faces: per face its record's index, the face, its map
        (height, width) float32 1/z and its levels (none when it has none)."""
        out = []
        for index, (face, size, (first, coarse, slot)) in enumerate(
            zip(self.faces.faces, self.faces.sizes(), self.faces.firsts, strict=True)
        ):
            count = pages_of(*size)
            one = {
                "index": self.faces.first_record + index,
                "face": face,
                "map": of_pages(self.read(loaded, "maps", first, count), *size),
            }
            if self.faces.levels:
                slots = self.read(loaded, "slots", slot, count)
                pages = self.read(loaded, "maps", coarse, coarse_pages(*size))
                one["levels"] = levels_of(slots, pages, *size)
            out.append(one)
        return out

    def times(self, loaded):
        """The SUN, FIT and LAMPS commands' times rows, read after the stop."""
        raw = loaded.region(TIMES)
        return times_rows(raw, self.row_views(), self.sent, MICROSECONDS)


def grid_of(size):
    """A DEPTH view's of `size`: its grid word and its tiles."""
    across, down = frame_grid(size)
    return raster_host.grid_word(size), across * down
