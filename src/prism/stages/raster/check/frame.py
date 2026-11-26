"""A whole frame by the raster class alone, stepped by the host in the thread's order
(COUNT, SUM, the middle pass, HIST, HSUM, PLACE, SETUP, FILL), its picture against
prism_reference's vertex-colour frame of the same view."""

import sys

import numpy as np

from prism.stages.raster import capacity, device
from prism.stages.raster.check.inputs import (
    CLUSTER,
    items_region,
    ranges_of,
    with_thread,
)
from prism.stages.raster.device import Raster
from prism.stages.raster.host import RasterHost, camera_area, heavy_page
from prism.stages.raster.model import bands, middle, numbers
from prism.stages.raster.model.frame import decoded
from prism.stages.raster.model.records import triangle_words
from prism_reference.raster.frames import rasterize
from prism_reference.scene.frame import frame_grid

K, S = numbers.K, numbers.S
TIMEOUT = 10.0  # seconds a command is waited for
PAGE = 4096  # a region page PLACE reads


def model_middle(entries, rows, cores, heavy, starts, ends):
    """The middle pass of model/ (the 32 x 32 grid's): (mid, totals)."""
    split = bands.items_of(entries, rows, heavy, starts, ends) if heavy else None
    mid = middle.middle(entries, rows, cores, bands=split)
    return mid, (entries if split is None else split[1]).sum(axis=0)


def reference_planes(scene):
    """The reference's padded frame as the five planes (depth, colour, triangle)."""
    frame = rasterize(scene)
    tri = triangle_words(frame["tri"]).view(np.float32)
    planes = [frame["depth"], *np.moveaxis(frame["colour"], 2, 0), tri]
    return np.stack(planes).astype(np.float32)


class Stepper:
    """The class loaded with an idle thread's regions; each pass a command."""

    def __init__(self, session, host):
        self.session, self.host, self.times = session, host, {}
        self.regions = {
            "camera": camera_area(
                host.scene, host.size, ranges_of(len(host.blocks), host.cores, "even")
            ),
            "heavy": heavy_page([]),
            "items": -(-host.sizes["kItemsRegionBytes"] // PAGE) * PAGE,  # whole pages
            "sums": capacity.sums_bytes(host.held),
        }
        program = with_thread(device.made(host), self.regions)
        self.loaded = session.load(program, deadline=1.0, thread="card")
        self.thread = self.loaded.threads[CLUSTER]
        self.bank, self.camera = self.thread.regions.address("camera")

    def step(self, name, handler, args):
        """One command on every core, waited for; its microseconds kept."""
        event = self.loaded.wait(
            self.loaded.submit(handler, (0, self.host.cores), args=args),
            timeout=TIMEOUT,
        )
        if event.kind != "done":
            raise RuntimeError(f"{name}: {event.kind}")
        self.times[name] = event.microseconds
        print(f"{name}: {event.microseconds:.2f} us", file=sys.stderr, flush=True)

    def words(self, tensor):
        """A tensor's pages as uint32 rows (read while the run is loaded)."""
        return self.session.read(tensor)[0].view(np.uint32)


def stepped(session, host, middle_of):
    """The frame's passes on the card; the host's middle pass between: the words of
    the frame's tensors, the commands' microseconds and the heavy tiles."""
    t, cores, sizes = host.tensors, host.cores, host.sizes
    across, down = frame_grid(host.size)
    tiles = across * down
    slices = -(-tiles // 16)
    run = Stepper(session, host)
    try:
        run.step("load_empty", Raster.load_empty, (t["empty_planes"],))
        heavy_word = (run.bank, 0)
        camera = (run.bank, run.camera)  # the camera area's address
        count = (t["mesh"], t["counters"], camera, heavy_word)
        run.step("count", Raster.count, count + (host.grid, t["profile"]))
        run.step("sum", Raster.sum, (t["counters"], t["slots"], "sums", cores, slices))
        counters = run.words(t["counters"])
        entries = counters[:, :tiles].astype(np.int64)
        rows = counters[:, sizes["kTiles"] : sizes["kTiles"] + tiles].astype(np.int64)
        heavy = bands.heavy_tiles(entries, rows, cores)
        cut = [tile for tile, _ in heavy]
        run.thread.write("heavy", heavy_page(cut))
        page_bytes = 64 * host.heavy
        hist = ("heavy", t["histograms"], page_bytes, t["profile"])
        run.step("hist", Raster.hist, hist)
        hsum = (len(cut), t["histograms"], t["hprefix"], "sums", cores, slices)
        run.step("hsum", Raster.hsum, hsum)
        halves = run.words(t["histograms"])[:, : 16 * len(cut)]
        halves = halves.copy().view(np.uint16).reshape(cores, len(cut), 2, 16)
        starts, ends = halves[:, :, 0].astype(np.int64), halves[:, :, 1].astype(
            np.int64
        )
        mid, totals = middle_of(entries, rows, cores, heavy, starts, ends)
        region = items_region(host, mid, totals, heavy, t["hprefix"].address)
        run.thread.write("items", region)
        place = ("items", t["directory"], cores, t["lists"], host.grid, t["profile"])
        run.step("place", Raster.place, place)
        list_slots = int(mid["slots"]) | S["kSetupPrefix"]
        setup = (t["mesh"], t["lists"], camera, t["slots"])
        setup += (list_slots, "items", t["profile"])
        run.step("setup", Raster.setup, setup)
        fill = (t["directory"], t["lists"], t["frame"][0], t["fill_profile"])
        run.step("fill", Raster.fill, fill + (host.grid,))
    finally:
        run.loaded.stop()
    words = np.concatenate([run.words(one).reshape(-1) for one in t["frame"]])
    return words, run.times, len(heavy)


def run(session, scene, options, middle_of=model_middle):
    """The frame of `scene` at `options` by the class: pixels whose five planes are
    not the reference's bit for bit, of the padded frame; the commands' us."""
    host = RasterHost(session, scene, options)
    host.prepare()
    words, times, heavy = stepped(session, host, middle_of)
    across, down = frame_grid(host.size)
    got = decoded(words, across, down)
    want = reference_planes(scene)
    differ = (got.view(np.uint32) != want.view(np.uint32)).any(axis=0)
    return {
        "pixels": int(differ.size),
        "pixels_differ": int(differ.sum()),
        "covered": int((want[4] >= 0).sum()),
        "heavy_tiles": heavy,
        "tiles": host.held.tiles,
        "microseconds": times,
    }
