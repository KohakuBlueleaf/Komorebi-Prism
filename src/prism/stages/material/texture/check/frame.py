"""A shaded frame by the raster and texture classes alone, stepped by the host: each
layer's raster passes with the shaded SETUP, then SHADE of each layer in the frame's
order (opaque; masked merged into it; glass blended over it); the picture against the
reference's shaded frame (model/expect.check)."""

import sys

import numpy as np

from prism.stages.material.texture import device as texture_device
from prism.stages.material.texture.device import Shade
from prism.stages.material.texture.host import TextureHost
from prism.stages.material.texture.model import expect
from prism.stages.raster.check.frame import TIMEOUT, Stepper, model_middle
from prism.stages.raster.check.inputs import items_region
from prism.stages.raster.device import Raster
from prism.stages.raster.host import RasterHost, heavy_page, layer_meshes
from prism.stages.raster.model import bands, numbers
from prism.stages.raster.model.frame import decoded
from prism_reference.post.display import to_srgb8
from prism_reference.raster.frames import picture
from prism_reference.scene.frame import frame_grid

S = numbers.S


def stepped_shaded(session, host, mesh, shade):
    """One layer's raster passes on the card, the host's middle pass between, its SETUP
    the shaded one on `mesh` (shaded blocks) and `shade`; the commands' us, by name."""
    t, cores, sizes = host.tensors, host.cores, host.sizes
    across, down = frame_grid(host.size)
    slices = -(-across * down // 16)
    run = Stepper(session, host)
    try:
        run.step("load_empty", Raster.load_empty, (t["empty_planes"],))
        camera = (run.bank, run.camera)  # the camera area's address
        count = (t["mesh"], t["counters"], camera, (run.bank, 0), host.grid)
        run.step("count", Raster.count, count + (t["profile"],))
        run.step("sum", Raster.sum, (t["counters"], t["slots"], "sums", cores, slices))
        counters = run.words(t["counters"])
        entries = counters[:, : across * down].astype(np.int64)
        rows = counters[:, sizes["kTiles"] : sizes["kTiles"] + across * down]
        rows = rows.astype(np.int64)
        heavy = bands.heavy_tiles(entries, rows, cores)
        run.thread.write("heavy", heavy_page([tile for tile, _ in heavy]))
        hist = ("heavy", t["histograms"], 64 * host.heavy, t["profile"])
        run.step("hist", Raster.hist, hist)
        hsum = (len(heavy), t["histograms"], t["hprefix"], "sums", cores, slices)
        run.step("hsum", Raster.hsum, hsum)
        halves = run.words(t["histograms"])[:, : 16 * len(heavy)]
        halves = halves.copy().view(np.uint16).reshape(cores, len(heavy), 2, 16)
        starts, ends = (halves[:, :, k].astype(np.int64) for k in (0, 1))
        mid, totals = model_middle(entries, rows, cores, heavy, starts, ends)
        region = items_region(host, mid, totals, heavy, t["hprefix"].address)
        run.thread.write("items", region)
        place = ("items", t["directory"], cores, t["lists"], host.grid, t["profile"])
        run.step("place", Raster.place, place)
        list_slots = int(mid["slots"]) | S["kSetupPrefix"]
        setup = (mesh, shade, t["lists"], camera, t["slots"], list_slots, "items")
        run.step("setup_shaded", Raster.setup_shaded, setup + (t["profile"],))
        fill = (t["directory"], t["lists"], t["frame"][0], t["fill_profile"])
        run.step("fill", Raster.fill, fill + (host.grid,))
    finally:
        run.loaded.stop()
    return run.times


def shade_all(session, texture, layers, grid):
    """SHADE of each layer in the frame's order on the texture class: (layer, merged
    1/z) pairs; the commands' us, by layer."""
    times, opaque = {}, layers["opaque"].tensors["directory"]
    loaded = session.load(texture_device.made(texture), deadline=1.0)
    try:
        for name, merged in (
            ("opaque", False),
            ("masked", "glass" in layers),
            ("glass", False),
        ):
            if name not in layers:
                continue
            tensors = layers[name].tensors
            merging = opaque if name != "opaque" else None
            words = texture.words(
                name, tensors["directory"], tensors["lists"], merging, merged
            )
            event = loaded.wait(
                loaded.submit(
                    Shade.shade,
                    (0, texture.cores),
                    args=words + (grid, 0, texture.examples["surface"]),
                ),
                timeout=TIMEOUT,
            )
            if event.kind != "done":
                raise RuntimeError(f"shade {name}: {event.kind}")
            times[name] = event.microseconds
            print(f"shade {name}: {event.microseconds:.2f} us", file=sys.stderr)
    finally:
        loaded.stop()
    return times


def run(session, scene, materials, options):
    """The shaded frame of `scene` (a view) on `materials`: expect.check's report of
    the card's picture, the commands' us by layer."""
    meshes = layer_meshes(scene, materials)
    layers, times = {}, {}
    for name, layer_scene, blocks in meshes:
        host = RasterHost(session, layer_scene, options)
        host.prepare()
        layers[name] = host
    held = layers["opaque"].held
    texture = TextureHost(
        session, scene, {**options, "materials": materials, "held": held}
    )
    texture.prepare()
    for name, layer_scene, blocks in meshes:
        host = layers[name]
        shade = texture.layers[name]["shade"]
        times[name] = stepped_shaded(session, host, host.tensor(blocks), shade)
    grid = layers["opaque"].grid
    times["shade"] = shade_all(session, texture, layers, grid)
    opaque = layers["opaque"]
    words = np.concatenate(
        [
            session.read(one)[0].view(np.uint32).reshape(-1)
            for one in opaque.tensors["frame"]
        ]
    )
    across, down = frame_grid(opaque.size)
    planes = decoded(words, across, down)
    colour = picture(np.ascontiguousarray(np.moveaxis(planes[1:4], 0, 2)), scene)
    report, _, _ = expect.check(scene, materials, to_srgb8(colour), to_srgb8)
    return {"check": report, "microseconds": times, "tiles": held.tiles}
