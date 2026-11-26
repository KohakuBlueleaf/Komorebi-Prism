"""The bytes a frame's command reads and writes, by kind, from the frame's own tables
(each core's directory items and their rows), the commands' words and the profiles'
counts of pages and bytes."""

import numpy as np

from prism.stages.direct.light.model.numbers import LH
from prism.stages.material.texture.model.numbers import SURFACE
from prism.stages.post.show.model.table import SHOW
from prism.stages.raster.model.numbers import K
from prism.stages.raster.sizes import PAGE, SLOT_BYTES, capacity_constants

ROW = K["kRowBytes"]  # a plane's row of a tile
PLANE = K["kOutPageBytes"]  # a plane of a tile
LIST_PAGE = K["kInPageBytes"]  # a list page
PLANES = K["kPlanes"]  # a tile's planes in the frame
TEXEL_PAGE = SURFACE["kTexPageBytes"]  # a texture, light or field page
SUM_ITEM = 64  # SUM's and HSUM's items (raster device.py)
SLICE_TILES = 16  # SUM's tiles a slice
SHADE_PLANES = {False: (PLANES, 1), True: (4 * PLANES, 2)}  # in, frame's out
SURFACE_OUT = SURFACE["kSurfacePlanes"]  # the surface's planes a lit item writes
LIGHT_IN = {False: LH["kLightItemPlanes"], True: LH["kLightGlassPlanes"]}
COLOUR = LH["kLightColourPlanes"]  # LIGHT's colour planes written
SHOW_IN = SHOW["kShowPlanes"]  # SHOW's planes read an item


def directory(words):
    """A layer's directory pages [cores, words] as each core's counts: items, items
    with a triangle, rows of every item and of those with one, list pages."""
    cores = words.shape[0]
    out = {n: np.zeros(cores, np.int64) for n in ("items", "full", "rows", "rows_full")}
    out["list_pages"] = words[:, K["kDirPages"]].copy()
    for core in range(cores):
        items = int(min(words[core, K["kDirItems"]], K["kDirMaxItems"]))
        ids = words[core, K["kDirIds"] : K["kDirIds"] + items]
        first = ids >> K["kItemRow0Shift"] & K["kItemRowMask"]
        end = ids >> K["kItemRow1Shift"] & K["kItemRowMask"]
        rows = np.where(end > 0, end - first, 32)
        full = (ids & K["kItemEmpty"]) == 0
        out["items"][core], out["full"][core] = items, int(full.sum())
        out["rows"][core], out["rows_full"][core] = rows.sum(), rows[full].sum()
    return out


def total(cpus, cpu, name):
    """The sum over cores of a CPU's count `name` (0 when it has none)."""
    got = cpus.get(cpu, {}).get("counts", {}).get(name)
    return int(np.sum(got)) if got is not None else 0


def moved(command, cpus, frame):
    """(read, written) {kind: bytes} of `command` in a frame: `cpus` its profile's
    counters (profiles.decoded), `frame` the frame's facts (cores, tiles, grid, held,
    heavy tiles a layer, directories by layer, merging layers, glass layer)."""
    name, layer = command.name, command.layer_name
    cores = frame["cores"]
    dirs = frame["directories"]
    match name:
        case "count":
            return {"mesh": total(cpus, "reader", "bytes")}, {
                "tables": total(cpus, "writer", "bytes")
            }
        case "setup":
            return {"mesh": total(cpus, "reader", "bytes")}, {
                "lists": total(cpus, "writer", "bytes")
            }
        case "sum":
            slices = -(-frame["tiles"] // SLICE_TILES)
            return {"tables": slices * 2 * cores * SUM_ITEM}, {
                "tables": slices * (cores + 2) * SUM_ITEM
            }
        case "hist":
            heavy = frame["heavy"][command.layer]
            return {}, {"tables": heavy * cores * SUM_ITEM}
        case "hsum":
            heavy = frame["heavy"][command.layer]
            return {"tables": heavy * cores * SUM_ITEM}, {
                "tables": heavy * (2 * cores + 2) * SUM_ITEM
            }
        case "place":
            sizes = capacity_constants(frame["held"])
            pages = sizes["LOW_PAGES"] + sizes["HIGH_PAGES"]
            full = int(dirs[layer]["full"].sum())
            return {"tables": cores * pages * PAGE}, {
                "lists": cores * (PAGE + SLOT_BYTES) + full * SLOT_BYTES
            }
        case "fill":
            return {"lists": total(cpus, "reader", "pages") * LIST_PAGE}, {
                "planes": int(dirs[layer]["rows"].sum()) * ROW * PLANES
            }
        case "shade":
            merging = layer in frame["merging"]
            planes_in, frame_out = SHADE_PLANES[merging]
            full = dirs[layer]
            read = {
                "lists": int(full["list_pages"].sum()) * LIST_PAGE,
                "planes": int(full["full"].sum()) * planes_in * PLANE,
                "texture pages": total(cpus, "pack", "pages") * TEXEL_PAGE,
            }
            out = (frame_out + SURFACE_OUT) * int(full["rows_full"].sum()) * ROW
            return read, {"planes": out}
        case "light" | "light_glass":
            glass = name == "light_glass"
            items = dirs[frame["glass"] if glass else frame["first"]]
            read = {
                "planes": int(items["items"].sum()) * LIGHT_IN[glass] * PLANE,
                "light pages": total(cpus, "pack", "pages") * TEXEL_PAGE,
                "field pages": total(cpus, "pack", "field_pages") * TEXEL_PAGE,
            }
            shown = total(cpus, "writer", "show_rows")
            if shown:
                return read, {"display": shown * ROW}
            return read, {"planes": COLOUR * int(items["rows"].sum()) * ROW}
        case "show":
            rows = total(cpus, "writer", "rows")
            return {"planes": SHOW_IN * rows * ROW}, {"display": rows * ROW}
        case "push":
            across, down = frame["grid"]
            return {}, {"display": across * down * PAGE}
    return {}, {}
