"""The pages a frame's lookups read, modelled on the host from the reference: textures
(SHADE), the shadow map with the background (LIGHT) and the field (LIGHT, the term
indirect); today's page passes checked against the card's counts
(measurements/account), an item's pages, the pages a core would keep within a frame and
across the forward path's frames. Written to
measurements/lookup_model/<scene>_<view>_<W>_<H>.json; one JSON line printed. Example:
python scripts/run/lookup_model.py --scene S --view overview --size 1920 1080 --frames
16 --terms indirect
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np

from prism.check.lookup import (
    QUARTER,
    SLOTS,
    cell_extent,
    frame_passes,
    item_shapes,
    kept_reads,
    layer_deal,
    new_caches,
    row_sets,
    tap_extent,
    texel_extent,
    today,
    voxel_extent,
    working_set,
)
from prism.loop.path import forward
from prism.stages.direct.light.model.numbers import LH, PAGE
from prism.stages.direct.light.model.table import light_table
from prism_common.paths import data_root
from prism_reference.direct.access import light_pages, light_surface
from prism_reference.direct.frame import OPTIONAL_TERMS, TERMS
from prism_reference.direct.lights import load as load_lights
from prism_reference.indirect.files import load_model
from prism_reference.material.access import (
    layer_pages,
    page_groups,
    shade_pixels,
    texture_firsts,
)
from prism_reference.material.kinds import MASKED, TRANSPARENT
from prism_reference.raster.setup import grid
from prism_reference.scene.camera import with_size
from prism_reference.scene.public.materials import load_materials
from prism_reference.scene.public.views import make_view

ROOT = Path(__file__).resolve().parents[2]
CORES = 120  # the cores the deal gives items to
KEPT_SLOTS = (64, 128, 256, 512)  # slots a core keeps across frames
LAYERS = ("opaque", "masked", "glass")
TABLES = ("textures", "shadow", "field")


def parse():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--scene", required=True, help="a public scene")
    parser.add_argument("--view", default="overview", help="a public scene's view")
    parser.add_argument("--size", type=int, nargs=2, required=True, help="W H")
    parser.add_argument("--frames", type=int, default=1, help="the forward path's")
    parser.add_argument(
        "--terms", nargs="*", default=[], choices=OPTIONAL_TERMS, help="past TERMS"
    )
    parser.add_argument("--cores", type=int, default=CORES)
    parser.add_argument("--out", type=Path, default=None, help="the record's file")
    return parser.parse_args()


def light_layout(lights, materials, terms, model):
    """The first pages of LIGHT's maps as its table holds them (light_table), and the
    field's blocks."""
    field = None if model is None else {"model": model, "scale": 1.0}
    words = light_table(lights, materials, terms, field)
    first = lambda name: int(words[LH[name] :].view(np.float32)[0]) - 1
    layout = {
        "shadow": first("kLtShadowFirst"),
        "octahedral": first("kLtOctaFirst"),
        "pages": int(words[LH["kLtPages"]]),
        "block": [LH["kFieldBlockX"], LH["kFieldBlockY"], LH["kFieldBlockZ"]],
    }
    if model is not None:
        layout["field"] = first("kLtFieldFirst")
    return layout


def light_decode(lights, layout, model):
    """Per table of LIGHT a function of pages to their group and grid coordinates: the
    shadow map's pages (group 0) and each background channel's (1 to 3); the field's
    blocks in x, y, z (group 0)."""
    shadow_across = lights["shadow_map"].shape[0] // PAGE
    octa_across = lights["octahedral"].shape[0] // PAGE

    def shadow(pages):
        octa = pages >= layout["octahedral"]
        local = np.where(octa, pages - layout["octahedral"], pages - layout["shadow"])
        channel = local // (octa_across * octa_across)
        local = local - channel * octa_across * octa_across
        across = np.where(octa, octa_across, shadow_across)
        group = np.where(octa, 1 + channel, 0)
        return group, np.stack([local % across, local // across, 0 * local], 1)

    out = {"shadow": shadow}
    if model is not None:
        blocks = -(-np.asarray(model["field_dims"]) // np.asarray(layout["block"]))

        def field(pages):
            local = pages - layout["field"]
            x, rest = local % blocks[0], local // blocks[0]
            z, y = rest % blocks[2], rest // blocks[2]
            return np.zeros_like(local), np.stack([x, y, z], 1)

        out["field"] = field
    return out


def texture_decode(materials, firsts):
    """Pages of the textures to their (texture, level) group and column, row."""
    group, column, row = page_groups(materials, firsts)

    def decode(pages):
        return group[pages], np.stack([column[pages], row[pages], 0 * pages], 1)

    return decode


def passes_of(sources, slots, cores):
    """Per core the passes of a table's sources (row sets, items, deal, unit, whether
    empty items make none), one source's after the other's, at `slots` slots."""
    out = [[] for _ in range(cores)]
    for sets, across, items, deal, unit, skip in sources:
        made = frame_passes(sets, across, items, deal, unit, slots, skip)
        for core in range(cores):
            out[core] += made[core]
    return out


def frame_tables(view, materials, lights, model, layout, firsts, cores, extents):
    """A frame's tables: per table its sources of passes (passes_of), its passes at
    SLOTS and its lookups a pixel; the textures' counts a layer; `extents`: an item's
    extent in the table's own unit."""
    across, _ = grid(view)
    kind = materials["kind"][materials["material"]]
    keeps = {
        "opaque": (kind != MASKED) & (kind != TRANSPARENT),
        "masked": kind == MASKED,
        "glass": kind == TRANSPARENT,
    }
    deals = {name: layer_deal(view, keep, cores) for name, keep in keeps.items()}
    surface = light_surface(view, materials, lights, glass=True)
    lit = light_pages(view, lights, surface, layout, model)
    where = shade_pixels(surface["layers"])
    sources, keyed, pixels, layers, kept = [], 0, 0, {}, []
    for name in LAYERS:
        layer = surface["layers"][name]
        pages, texels = layer_pages(
            materials, surface["prepared"], layer, where[name], firsts, name == "masked"
        )
        source = (row_sets(pages, across), across, *deals[name], 32, True)
        sources.append(source)
        layers[name] = today(passes_of([source], SLOTS, cores))
        layers[name]["texels"] = int((pages[..., :3] >= 0).sum())
        keyed += int((pages >= 0).sum())
        if extents:
            kept.append(([i for i in deals[name][0] if i[3] > 0], texels))
        pixels += int(where[name].sum())
    out = {
        "textures": {
            "sources": sources,
            "layers": layers,
            "lookups": {
                "pixels": pixels,
                "gathered": 3,
                "keys": round(keyed / max(pixels, 1), 4),
            },
        }
    }
    if extents:
        out["textures"]["extent"] = texel_extent(kept)
    covered = int(surface["covered"].sum())
    for name, gathered in (("shadow", 4), ("field", 24)):
        if name not in lit:
            continue
        valid = lit[name][surface["covered"]] >= 0
        source = (row_sets(lit[name], across), across, *deals["opaque"], QUARTER, False)
        out[name] = {
            "sources": [source],
            "lookups": {
                "pixels": covered,
                "gathered": gathered,
                "keys": round(float(valid.sum() / max(covered, 1)), 4),
            },
        }
    if extents:
        out["shadow"]["extent"] = tap_extent(deals["opaque"][0], lit["taps"])
        if "field" in out:
            out["field"]["extent"] = voxel_extent(deals["opaque"][0], lit["voxels"])
            out["field"]["extent"]["cells"] = cell_extent(
                deals["opaque"][0], lit["cells"]
            )
    background = lit["shadow"][~surface["covered"]] >= 0
    out["shadow"]["lookups"]["background_pixels"] = int((~surface["covered"]).sum())
    out["shadow"]["lookups"]["background_keys"] = int(background.sum())
    for table in out.values():
        table["passes"] = passes_of(table["sources"], SLOTS, cores)
    return out


def card_counts(scene, view, size, terms):
    """What the card counted in measurements/account's record of the case (SHADE a
    layer, LIGHT), summed over the cores; None without a record."""
    pipeline = "gi" if "indirect" in terms else "lit"
    name = "_".join([scene, view, *map(str, size), pipeline])
    path = ROOT / "measurements" / "account" / f"{name}.json"
    if not path.exists():
        return None, name
    record = json.loads(path.read_text())
    out = {}
    for stage in record["stages"]:
        items = stage.get("items") or {}
        total = {k: float(np.sum(v)) for k, v in items.items() if isinstance(v, list)}
        if stage["command"] == "shade":
            out[f"shade.{stage['layer']}"] = total
        elif stage["command"] == "light":
            out["light"] = total
    return out, name


def ratio(model, card):
    """The model's number, the card's and their ratio."""
    return {
        "model": model,
        "card": card,
        "ratio": round(model / card, 4) if card else None,
    }


def check(first, card):
    """The model's first frame against the card's counts: SHADE's pages, passes and
    texels a layer and over the layers, LIGHT's pages and passes, the field's."""
    out = {}
    layers = first["textures"]["layers"]
    totals = {"pages": 0, "passes": 0, "texels": 0, "card_pages": 0.0}
    for name, got in layers.items():
        counted = card.get(f"shade.{name}")
        if counted is None:
            continue
        out[f"shade.{name}"] = {
            k: ratio(got[k], counted.get(k, 0.0)) for k in ("pages", "passes", "texels")
        }
        for k in ("pages", "passes", "texels"):
            totals[k] += got[k]
        totals["card_pages"] += counted.get("pages", 0.0)
    out["shade.pages"] = ratio(totals["pages"], totals["card_pages"])
    light = card.get("light", {})
    for table, key in (("shadow", ""), ("field", "field_")):
        if table in first:
            got = today(first[table]["passes"])
            out[f"light.{key}pages"] = ratio(
                got["pages"], light.get(f"{key}pages", 0.0)
            )
            out[f"light.{key}passes"] = ratio(
                got["passes"], light.get(f"{key}passes", 0.0)
            )
    return out


def main():
    args = parse()
    started = time.perf_counter()
    terms = (*TERMS, *args.terms)
    name = f"{args.scene}_{args.view}"
    base = make_view(name, data_root())
    materials = load_materials(name, data_root())[0]
    lights = load_lights(name, data_root())
    model = None
    if "indirect" in terms and "indirect" in lights:
        model = load_model(lights["indirect"])
    layout = light_layout(lights, materials, terms, model)
    firsts = texture_firsts(materials)
    decode = light_decode(lights, layout, model)
    decode["textures"] = texture_decode(materials, firsts)
    cameras = forward(base["camera"], max(args.frames, 1))
    caches = {(t, s): new_caches(args.cores) for t in TABLES for s in KEPT_SLOTS}
    across_frames = {(t, s): [] for t in TABLES for s in KEPT_SLOTS}
    record = {}
    for number, camera in enumerate(cameras):
        view = with_size({**base, "camera": camera}, args.size)
        tables = frame_tables(
            view, materials, lights, model, layout, firsts, args.cores, number == 0
        )
        if number == 0:
            record = {
                t: {
                    "today": today(tables[t]["passes"]),
                    "item": item_shapes(tables[t]["passes"], decode[t]),
                    "lookups": tables[t]["lookups"],
                    "extent": tables[t]["extent"],
                    "working_set": working_set(tables[t]["passes"]),
                    "kept_in_frame": dict(
                        zip(
                            ("reads", "asked"),
                            kept_reads(
                                tables[t]["passes"], new_caches(args.cores), SLOTS
                            ),
                        )
                    ),
                }
                for t in TABLES
                if t in tables
            }
            record["textures"]["layers"] = tables["textures"]["layers"]
            first = tables
        if args.frames <= 1:
            break
        for (t, slots), kept in caches.items():
            if t not in tables:
                continue
            passes = tables[t]["passes"]
            if slots != SLOTS:
                passes = passes_of(tables[t]["sources"], slots, args.cores)
            across_frames[(t, slots)].append(kept_reads(passes, kept, slots))
        print(f"frame {number}: {time.perf_counter() - started:.0f} s", flush=True)
    for t in record:
        kept = record[t]["kept_in_frame"]
        kept["share_of_today"] = round(
            kept["reads"] / max(record[t]["today"]["pages"], 1), 4
        )
        frames = {}
        for slots in KEPT_SLOTS:
            runs = across_frames[(t, slots)][1:]
            if not runs:
                continue
            reads = sum(r for r, _ in runs)
            asked = sum(a for _, a in runs)
            frames[str(slots)] = {
                "reads_a_frame": round(reads / len(runs), 1),
                "asked_a_frame": round(asked / len(runs), 1),
                "hit_rate": round(1 - reads / max(asked, 1), 4),
            }
        if frames:
            record[t]["kept_across_frames"] = frames
    card, account = card_counts(args.scene, args.view, args.size, terms)
    out = {
        "case": {
            "scene": args.scene,
            "view": args.view,
            "size": list(args.size),
            "terms": list(terms),
            "frames": len(cameras) if args.frames > 1 else 1,
            "path": "forward",
            "cores": args.cores,
            "slots": SLOTS,
            "field": model is not None,
        },
        "layout": layout,
        "check": {"account": account, **(check(first, card) if card else {})},
        "tables": record,
        "seconds": round(time.perf_counter() - started, 1),
    }
    path = args.out or ROOT / "measurements" / "lookup_model" / (
        "_".join([args.scene, args.view, *map(str, args.size)]) + ".json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1) + "\n")
    summary = {"case": out["case"], "check": out["check"]}
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
