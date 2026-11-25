"""SHOW's host side for one scene on one session: the display tensor of a capacity, the
thresholds' table (of the display's transfer, a control), the push armed for a
frame's grid, and the picture from the pushed image (or the display read back)."""

import time
from functools import partial

import numpy as np

from prism.core.capacity import Capacity, capacity, default_capacity, narrow, need
from prism.core.control import Control
from prism.core.implementation import Host
from prism.stages.post.show.model.pages import (
    FramePages,
    padded_image,
    untile,
)
from prism.stages.post.show.model.table import SHOW, most_gamma, show_table
from prism.stages.post.show.unit import P as PUSH
from prism.stages.raster.model import numbers
from prism_reference.post.display import (
    GAMMA,
    to_power8,
    to_srgb_standard8,
)
from prism_reference.scene.frame import frame_grid, frame_size

K = numbers.K
PAGE_WORDS = SHOW["kShowPageBytes"] // 4  # a display page: a tile's pixels
PROFILE_WORDS = SHOW["kShowProfBytes"] // 4  # a core's profile page
PUSH_TIMEOUT_S = 2.0  # a frame's wait for the pushed image
PUSH_SPIN_S = 20e-3  # its looks without a pause: longer than a frame
POWER, SRGB = "power", "srgb"  # the display's transfers
TRANSFERS = ((POWER, "power"), (SRGB, "sRGB"))
LEAST_GAMMA = 1.0


def table_region(table):
    """The table's region: its words, then zeros to the region's page."""
    words = np.zeros(SHOW["kShowPageBytes"] // 4, dtype=np.uint32)
    words[: len(table)] = table
    return words


class ShowHost(Host):
    """What SHOW needs on the host for `scene` on `session`: after `prepare()`, the
    capacity, the display and profile tensors, the thresholds' table. Options: size,
    cores, recount, capacity (as the raster stage's); push (True: the image pushed,
    False: the display read back); transfer (power, srgb) and gamma (of power)."""

    pictures = True

    def __init__(self, session, scene, options):
        self.session = session
        self.scene = scene
        self.cores = options.get("cores") or session.ranks
        self.size = tuple(options.get("size") or frame_size(scene))
        self.recount = bool(options.get("recount", False))
        self.at_least = options.get("capacity") or default_capacity()
        self.push = bool(options.get("push", True))
        self.loaded = None  # the run whose numbers are written
        self.transfer = None  # the push of the armed grid
        self.armed = None  # its grid (TX, TY)
        self.waits = []  # each pushed frame's wait for its image, ms
        self.conversion = options.get("transfer", POWER)
        self.gamma = float(options.get("gamma", GAMMA))

    def prepare(self):
        """The capacity of the scene's frame (as the raster stage's), the table, the
        display (a page a tile of the capacity) and profile tensors."""
        held = capacity([self.size], at_least=self.at_least)
        self.held = held._replace(recount=self.recount, cores=self.cores)
        self.table = self.thresholds()
        self.tensors = {
            "display": self.tensor(np.zeros((self.held.tiles, PAGE_WORDS))),
            "profile": self.tensor(np.zeros((self.cores, PROFILE_WORDS))),
            "directory": self.tensor(np.zeros((self.cores, K["kDirBytes"] // 4))),
        }
        self.examples = {
            "directory": self.tensors["directory"],
            "display": self.tensors["display"],
            "profile": self.tensors["profile"],
            "target": self.tensors["display"],
        }

    def thresholds(self):
        """The table of the transfer and gamma held (today's table for power at
        GAMMA)."""
        if self.conversion == SRGB:
            return show_table(to_srgb_standard8)
        if self.gamma == GAMMA:
            return show_table()
        return show_table(partial(to_power8, gamma=self.gamma))

    def controls(self):
        """The display's transfer (power or sRGB) and the power's gamma."""
        return [
            Control(
                "transfer",
                "Display transfer",
                "choice",
                self.conversion,
                choices=TRANSFERS,
                help="power: x to the 1 / gamma; sRGB: the standard piecewise curve",
            ),
            Control(
                "gamma",
                "Gamma",
                "range",
                self.gamma,
                (LEAST_GAMMA, most_gamma()),
                help="of the power transfer; its most is what the display's "
                "conversion holds",
            ),
        ]

    def set(self, loaded, name, value):
        """The transfer or the gamma: the table made again and written for the next
        frame, kept in the options for a reload."""
        if name not in ("transfer", "gamma"):
            return f"no control {name!r}"
        transfer, gamma = self.conversion, self.gamma
        if name == "transfer":
            self.conversion = value
        else:
            self.gamma = float(value)
        try:
            self.table = self.thresholds()
        except ValueError as error:
            self.conversion, self.gamma = transfer, gamma
            return str(error)
        loaded.options[name] = value
        loaded.write("show_table", self.table)
        return None

    def tensor(self, rows):
        """A row-major uint32 array as a DRAM tensor, a page a row."""
        return self.session.tensor(np.asarray(rows, dtype=np.uint32), "uint32")

    def thread_numbers(self):
        """The unit's numbers: the display's and the profile's addresses, the push."""
        return {
            "show_display": self.tensors["display"].address,
            "show_profile": self.tensors["profile"].address,
            "show_pushes": int(self.push),
        }

    def need(self, size):
        """The tiles of a frame of `size`, as the raster stage's: its display's
        pages."""
        return Capacity(need([size]), not narrow(frame_grid(size)))

    def view(self, loaded, camera, size):
        """The unit's numbers once a run; with the push, the push armed for the
        frame's grid (again when it changed) and the frame's key into its words."""
        if self.loaded is not loaded:
            loaded.numbers(self.thread_numbers())
            self.loaded, self.armed = loaded, None
        self.size = tuple(size)
        if not self.push:
            return
        grid = frame_grid(self.size)
        if grid != self.armed:
            self.arm_push(loaded, grid)
        key = np.array([self.transfer.arm()], dtype=np.uint32)
        loaded.write("show_push", key, 4 * PUSH["SHOW_PUSH_KEY"])

    def arm_push(self, loaded, grid):
        """The PUSH of a frame's display pages (the tiles of `grid` (TX, TY)) into the
        unit's push words; the last one's slot given back."""
        if self.transfer is not None:
            self.transfer.close()
        across, down = grid
        self.transfer = transfer = self.session.channel_transfer(
            FramePages.of(self.tensors["display"], across * down), push=True
        )
        entry = transfer.entry
        words = np.zeros(PUSH["SHOW_PUSH_BYTES"] // 4, dtype=np.uint32)
        words[PUSH["SHOW_PUSH_HEADER"]] = entry.handler | entry.field << 24
        words[PUSH["SHOW_PUSH_GROUP"]] = entry.group[0] | entry.group[1] << 16
        at = PUSH["SHOW_PUSH_ARGS"]
        words[at : at + len(entry.args)] = entry.args
        loaded.write("show_push", words)
        self.armed = grid

    def picture(self, loaded):
        """The displayed frame (H, W, 4) uint8 of the frame's size: the pushed image,
        or (without the push) the display tensor read back."""
        if not self.push:
            return self.display(loaded)
        grid = frame_grid(self.size)
        began = time.perf_counter()
        if not self.transfer.wait(PUSH_TIMEOUT_S, PUSH_SPIN_S):
            raise TimeoutError("the pushed image did not arrive")
        self.waits.append((time.perf_counter() - began) * 1e3)
        return self.cropped(self.transfer.data, grid)

    def display(self, loaded):
        """The display tensor's pages of the frame read back, as picture() gives."""
        grid = frame_grid(self.size)
        pages = loaded.session.read(self.tensors["display"], pages=grid[0] * grid[1])
        return self.cropped(pages, grid)

    def cropped(self, pages, grid):
        """The display's pages of `grid` untiled into the image kept for that grid, the
        frame's size of it (overwritten by the next picture)."""
        width, height = self.size
        kept = getattr(self, "kept", None)  # (grid, its padded image)
        if kept is None or kept[0] != tuple(grid):
            self.kept = kept = (tuple(grid), padded_image(grid))
        return untile(pages, kept[1], grid)[:height, :width]

    def readings(self):
        """What the page shows of the picture: how it reaches the host and the last
        wait for the pushed image."""
        last = round(self.waits[-1], 3) if self.push and self.waits else None
        return {
            "title": "Display",
            "values": [
                {
                    "name": "picture",
                    "value": "pushed by the card" if self.push else "read back",
                    "unit": "",
                },
                {"name": "push wait ms", "value": last, "unit": "ms"},
            ],
            "missing": None if self.push else "no push: the display is read back",
        }
