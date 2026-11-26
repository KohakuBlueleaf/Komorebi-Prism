"""The field update's host side for one scene on one session: the lights at the sun, the
field model, the light pages (the shadow map's, then the field's), the regions'
contents, the numbers, the sun's words written live, the bounces a control, the steps
submitted and what the update leaves read back."""

import time

import numpy as np
from komorebi import formats

from prism.core.control import Control
from prism.core.implementation import Command
from prism.core.unit import BESIDE, FRAMES
from prism.program.assemble import MissingSlot
from prism.stages.direct.light.model.sun import scene_box, sun_lights
from prism.stages.direct.light.model.terms import light_pages
from prism.stages.indirect.field_update.model.header import header, sun_words
from prism.stages.indirect.field_update.model.numbers import (
    F32,
    PAGE_TEXELS,
    STEPS,
    SUN_FIRST,
    TILE,
    X_PAGE,
    Y_PAGE,
)
from prism.stages.indirect.field_update.model.regions import (
    counts,
    elements_region,
    work_layout,
)
from prism.stages.indirect.transport.host import scene_name
from prism.stages.indirect.transport.plan.emulate import x_tiles
from prism_common.paths import data_root
from prism_reference.direct.lights import BOUNCES, bounce_count, moved
from prism_reference.direct.lights import load as load_lights
from prism_reference.indirect.files import load_model
from prism_reference.indirect.hmatrix.apply import apply
from prism_reference.scene.public.materials import load_materials
from prism_reference.scene.public.views import make_view

COMMAND = "update"
VIEW = "overview"  # the view whose scene the sun's shadow map is made of
PAGES = "light.field"  # the light pages, when a host gives them
SCALE = "light.field_scale"  # the last update's scale, for the host that reads it
SCALE_COMMAND = "field_scale"  # the command returning the last update's scale word
MS = 1e3


def sun_moved(scene, sun):
    """The scene's lights, with the sun at `sun` (azimuth, elevation; None: as loaded)
    and its shadow map as the reference makes it."""
    data = data_root()
    lights = load_lights(scene, data)
    if sun is None:
        return lights
    view = f"{scene}_{VIEW}"
    return moved(lights, make_view(view, data), load_materials(view, data)[0], *sun)


class FieldUpdateHost:
    """What the update needs on the host for `scene` (a name, or a view's scene with
    the option `name`) on `session`: after `prepare()`, the lights, the field model and
    the regions' contents; after `connect()`, the light pages tensor. In a loop, an
    update after each change of the option `sun` (azimuth, elevation) or of the
    bounces (the option `bounces`, a control). Option `update_beside`: its unit on the
    cluster beside the frames', the update submitted beside them, the field's pages
    twice (the half LIGHT reads, the half the update writes)."""

    def __init__(self, session, scene, options):
        self.session = session
        self.scene = scene_name(scene, options)
        self.box = None if isinstance(scene, str) else scene_box(scene)
        self.cores = options.get("cores") or session.ranks
        self.sun = options.get("sun")
        self.bounces = bounce_count(options.get("bounces", BOUNCES))
        self.beside = bool(options.get("update_beside", False))
        self.cluster = BESIDE if self.beside else FRAMES
        self.halves = 2 if self.beside else 1  # the field's pages in the light pages
        self.half = 0  # the half that holds the last field made
        self.running = False  # an update beside the frames sent, not served yet
        # (sun, bounces) the light pages' field is of (sun None: the files'): prepare()
        self.made = None
        self.asked = None  # (sun, bounces) of the update sent
        # slot light.field_scale (half: the half of the field's pages it is in)
        self.given = {"updates": 0, "scale": None, "half": 0}
        self.sent_at = None  # when the update sent was asked for
        self.last_ms = None  # the last update's round trip on the host, ms

    def prepare(self):
        """The lights at the sun, the model, the regions' contents, the light pages'
        layout."""
        self.own_lights = sun_moved(self.scene, None)
        self.made = (None, bounce_count(self.own_lights.get("bounces", BOUNCES)))
        self.lights = self.own_lights
        if self.sun is not None:
            self.lights = sun_moved(self.scene, self.sun)
        if "indirect" not in self.lights:
            raise ValueError(f"{self.scene}: no indirect field model in the data root")
        self.model = load_model(self.lights["indirect"])
        self.counts = counts(self.model)
        self.elements, element_offsets = elements_region(self.model, self.lights)
        self.work_offsets, self.work_bytes = work_layout(self.model)
        self.offsets = element_offsets | self.work_offsets
        empty = {"pages": np.zeros((self.counts["pages"], PAGE_TEXELS), np.uint32)}
        self.own, self.first = light_pages(self.lights, empty)

    def header_words(self):
        """The header region's words for the lights and bounces held."""
        return header(self.model, self.lights, self.offsets, self.bounces)

    def slots(self):
        """The field's scale as the last update left it (slot light.field_scale): the
        updates made, the scale (np.float32; None before the first)."""
        return {SCALE: self.given}

    def connect(self, assembled):
        """The light pages: slot light.field's tensor when a host gives it (ValueError
        when it is smaller than the layout), else pages of its own; x and y of the
        passes: the tensors of elements.radiance and elements.irradiance, of the
        model's tiles."""
        try:
            self.pages = assembled.slot(PAGES)
        except MissingSlot:
            self.pages = self.session.tensor(self.own, "uint32")
        self.own = None
        end = self.first["field"] + self.halves * self.counts["pages"]
        if self.pages.pages != end:
            raise ValueError(
                f"the light pages hold {self.pages.pages} pages, the update's layout "
                f"{end} (its field from page {self.first['field']})"
            )
        x = assembled.slot("elements.radiance")
        y = assembled.slot("elements.irradiance")
        tiles = self.counts["tiles"]
        for name, tensor, page in (("x", x, X_PAGE), ("y", y, Y_PAGE)):
            if tensor.pages != tiles or tensor.page_bytes != page:
                raise ValueError(
                    f"{name} of the passes: {tensor.pages} pages of "
                    f"{tensor.page_bytes} B, the update needs {tiles} of {page} B"
                )
        self.x, self.y = x, y

    def bind(self, loaded):
        """Its numbers: the cores, the light pages for the shadow map and the field,
        x and y of the passes."""
        self.loaded = loaded
        loaded.numbers(
            {
                "update_cores": self.cores,
                "update_shadow": self.pages.address,
                "update_shadow_first": self.first["shadow"],
                "update_field": self.pages.address,
                "update_field_first": self.field_first(self.written()),
                "update_x": self.x.address,
                "update_y": self.y.address,
            }
        )

    def written(self):
        """The half of the field's pages the next update writes: the other one beside
        the frames, else the one."""
        return 1 - self.half if self.beside else 0

    def field_first(self, half):
        """The light page the field's half `half` begins at."""
        return self.first["field"] + half * self.counts["pages"]

    def set_sun(self, lights, bounces):
        """The sun's words of `lights` and `bounces` into the live header region, and
        its shadow map into the light pages."""
        self.lights, self.bounces = lights, bounce_count(bounces)
        words = sun_words(lights, self.bounces)
        self.loaded.write("field_header", words, 4 * SUN_FIRST)
        pages, _ = light_pages(lights)
        shadow = pages[: self.first["octahedral"]]
        self.session.write(self.pages, shadow.view(np.uint8).reshape(len(shadow), -1))

    def commands(self, loaded):
        """The whole update, when the loop's sun or the bounces are not those the
        field was made for: the sun's words of the lights at it (the shadow map the
        card's), the bounces and the half it writes given first; beside the frames,
        none while the one sent runs."""
        if self.running:
            return []
        sun = loaded.options.get("sun")
        sun = None if sun is None else tuple(float(n) for n in sun)
        if (sun, self.bounces) == self.made:
            return []
        lights = self.own_lights
        if sun is not None:
            lights = sun_lights(self.own_lights, self.box, *sun)
        self.lights, self.asked = lights, (sun, self.bounces)
        loaded.write("field_header", sun_words(lights, self.bounces), 4 * SUN_FIRST)
        loaded.number("update_field_first", self.field_first(self.written()))
        self.sent_at = time.perf_counter()
        self.running = self.beside
        return [Command(COMMAND, (STEPS["all"],), row=False, beside=self.beside)]

    def served(self, loaded, command, code):
        """An update that came back 0: its sun and bounces kept, its round trip, the
        half it wrote, its scale asked for (the command field_scale) and given; none
        otherwise."""
        if command != COMMAND:
            return
        self.running = False
        if code != 0:
            return
        self.last_ms = (time.perf_counter() - self.sent_at) * MS
        self.made = self.asked
        self.half = self.written()
        self.given["half"] = self.half
        bits = loaded.serve(SCALE_COMMAND)
        self.given["scale"] = np.array([bits], np.uint32).view(F32)[0]
        self.given["updates"] += 1

    def controls(self):
        """The bounces: the passes of the transport's matrix an update applies."""
        return [
            Control(
                "bounces",
                "Bounces (H-matrix passes)",
                "count",
                self.bounces,
                limits=(0, None),
                help="the field updated again with this many applies of the matrix",
            )
        ]

    def set(self, loaded, name, value):
        """The bounces, kept in the options (and a reload); the update sent again
        before the next frame."""
        if name != "bounces":
            return f"no control {name!r}"
        self.bounces = bounce_count(value)
        loaded.options["bounces"] = self.bounces
        return None

    def readings(self):
        """What the page shows of the updates: their count, the last one's passes and
        its round trip on the host; what is read only after the stop."""
        return {
            "title": "Field update",
            "values": [
                {"name": "updates", "value": self.given["updates"], "unit": ""},
                {"name": "passes", "value": self.made[1], "unit": ""},
                {"name": "host ms", "value": self.last_ms, "unit": "ms"},
            ],
            "missing": "the card's time of an update is read when the run stops",
        }

    def submit(self, step):
        """One `update` command of `step` (STEPS' name): its code."""
        return self.loaded.serve(COMMAND, [STEPS[step]])

    def run(self, stepped, on_x=None):
        """One update: the whole of it in one command, or (`stepped`, passes above 0)
        sources, each pass's apply on the host (float32), finish. `on_x(p, x)`: each
        pass's x as the host read it. (code, the host's seconds by part)."""
        began = time.perf_counter()
        host = {"commands_s": 0.0, "read_s": 0.0, "apply_s": 0.0, "write_s": 0.0}

        def command(step):
            start = time.perf_counter()
            code = self.submit(step)
            host["commands_s"] += time.perf_counter() - start
            return code

        if not stepped or self.bounces == 0:
            code = command("all")
        else:
            code = command("sources")
            for p in range(self.bounces):
                if code != 0:
                    break
                x, parts = self.host_apply()
                for key, value in parts.items():
                    host[key] += value
                if on_x is not None:
                    on_x(p, x)
                code = command("pass")
            if code == 0:
                code = command("finish")
        host["s"] = time.perf_counter() - began
        return code, {key: round(value, 4) for key, value in host.items()}

    def host_apply(self):
        """The host in the apply's place: x read from its tensor, y = M x in float32,
        y written to its tensor. x and the seconds: read, apply, write."""
        began = time.perf_counter()
        x = self.x_of()
        read = time.perf_counter()
        y = apply(self.model["blocks"], self.model["weights"], x)
        applied = time.perf_counter()
        self.session.write(self.y, y_pages(y))
        ended = time.perf_counter()
        parts = {
            "read_s": read - began,
            "apply_s": applied - read,
            "write_s": ended - applied,
        }
        return x, parts

    def x_of(self):
        """x's tensor read back as [N, 3] float32 (rows 0 to 2 of its bf16 tiles)."""
        tiles = self.counts["tiles"]
        (raw,) = self.session.read(self.x)
        bits = np.ascontiguousarray(raw).view(np.uint16).reshape(tiles, TILE * TILE)
        values = (bits.astype(np.uint32) << 16).view(F32)
        return formats.untilize(values, TILE, TILE * tiles)[:3].T.copy()

    def field_pages(self):
        """The field's pages read from the light pages while the run is loaded."""
        (raw,) = self.session.read(
            self.pages, first=self.field_first(self.half), pages=self.counts["pages"]
        )
        return np.ascontiguousarray(raw).view(np.uint32).reshape(-1, PAGE_TEXELS)


def y_pages(y):
    """y [N, 3] as the float32 tile tensor's pages [tiles, 4,096] uint8."""
    raw, _ = formats.to_bytes(x_tiles(np.asarray(y, F32)), "float32", "tile")
    return np.asarray(raw).reshape(-1, Y_PAGE)
