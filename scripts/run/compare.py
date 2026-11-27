"""Our pictures of a glTF scene beside Cycles reading the same file: the truth (kept, made
once a file, camera, size and sample count), the reference's direct light by pass, and
with --card a preset's picture on a card; numbers by pass, one strip, named crops; every
file written under --out (and the truth's cache), one JSON line printed (no card unless
--card)."""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from compare_crops import crops_of
from compare_frame import INDIRECT, card_linear, frame_of
from compare_pictures import (
    crop_box,
    cropped,
    display_numbers,
    heat,
    pass_numbers,
    sheet,
    strip,
    whole_numbers,
)
from PIL import Image

from prism_common.paths import data_root
from prism_reference.direct.described.direct import described_lights, direct_light
from prism_reference.io.png import write_png
from prism_reference.material.surface import MOST_TRIANGLES, surface, visibility
from prism_reference.post.described import displayed
from prism_reference.post.display import to_srgb_standard8
from prism_reference.scene.artist.entry import camera_node
from prism_reference.scene.artist.opened import (
    file_key,
    opened_table,
    scene_files,
    scene_name,
)
from prism_reference.scene.description.flatten import flatten
from prism_reference.scene.importers import gltf
from prism_reference.trace.tree import build

HERE = Path(__file__).resolve().parent
BLENDER_SCRIPTS = HERE.parent / "blender"
BLENDER_VARIABLE = "PRISM_BLENDER"  # Blender's executable, else `blender`
CACHE_VARIABLE = "PRISM_COMPARE_CACHE"  # the truths' folder, else <out>/truth
LOCK_VARIABLE = "PRISM_DEVLOCK"  # a card lock's command, wrapping the card's run
RUNNER_VARIABLE = "PRISM_CARDRUN"  # a card's run wrapper, inside the lock
GLTF_BLEND = "scene_gltf.blend"  # from_gltf.py's file, beside the .glb or cached
BACKGROUND_DEPTH = 1e9  # Cycles' depth at or past it: no surface
REGISTERED = 1e-3  # positions within this share of the diagonal: the same point
METALLIC_UNDER = 0.01  # the base colour is compared where metallic is under this
LOCK_WAIT = 3600


def picture_of(path):
    """A PNG's RGB bytes (H, W, 3), whatever its filters and channels."""
    return np.asarray(Image.open(path).convert("RGB"))


def labelled_path(text):
    """LABEL=PATH as (label, path)."""
    label, sep, path = text.partition("=")
    if not sep or not label or not path:
        raise argparse.ArgumentTypeError(f"{text!r}: not LABEL=PATH")
    return label, path


def blender_line(arguments, timeout, gpu):
    """Runs Blender with the arguments; its script's JSON line, or SystemExit."""
    command = [os.environ.get(BLENDER_VARIABLE, "blender"), "--background"]
    environment = dict(os.environ)
    if gpu is not None:
        environment["CUDA_VISIBLE_DEVICES"] = str(gpu)
    try:
        done = subprocess.run(
            command + arguments,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=environment,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise SystemExit(f"Blender stopped after {timeout} s: {arguments}") from error
    lines = [ln[ln.find('{"') :] for ln in done.stdout.splitlines() if '{"' in ln]
    if done.returncode or not lines:
        tail = "\n".join((done.stdout + done.stderr).strip().splitlines()[-8:])
        raise SystemExit(f"Blender exit {done.returncode}: {arguments}\n{tail}")
    return json.loads(lines[-1])


def source_of(scene, data):
    """(the .glb, its key, the name of a table scene opened from it or None) of a file
    path or of an opened scene's name."""
    path = Path(scene)
    if path.suffix in (".glb", ".gltf"):
        glb = path.resolve()
        key = file_key(glb)
        names = [
            name
            for name, entry in opened_table(data).items()
            if entry.get("opened", {}).get("key") == key
        ]
        return glb, key, (names[0] if names else None)
    entry = opened_table(data).get(scene)
    if entry is None or "source" not in entry:
        raise SystemExit(f"{scene!r}: not a glTF file nor an opened scene of {data}")
    glb = Path(entry["source"]["file"])
    key = file_key(glb)
    if key != entry.get("opened", {}).get("key"):
        raise SystemExit(f"{scene!r}: its source {glb} changed since it was opened")
    return glb, key, scene


def gltf_blend(glb, folder, timeout):
    """from_gltf.py's .blend of the file: the one beside it when newer than the
    file's own files, else made (once) in `folder`; its path."""
    beside = glb.parent / GLTF_BLEND
    newest = max(f.stat().st_mtime for f in scene_files(glb))
    if beside.exists() and beside.stat().st_mtime > newest:
        return beside
    kept = folder / GLTF_BLEND
    if kept.exists() and kept.stat().st_mtime > newest:
        return kept
    folder.mkdir(parents=True, exist_ok=True)
    script = str(BLENDER_SCRIPTS / "from_gltf.py")
    stem = str(glb.with_suffix(""))
    arguments = ["--factory-startup", "--python", script, "--", stem, str(kept)]
    blender_line(arguments, timeout, None)
    return kept


def truth_of(glb, key, args, cache):
    """The truth's planes and Blender's own picture, made when not kept; its record."""
    folder = cache / scene_name(glb, key)
    view = re.sub(r"[^A-Za-z0-9]+", "_", args.camera).strip("_") if args.camera else ""
    w, h = args.size
    stem = folder / f"truth_{view or 'render'}_{w}x{h}_s{args.samples}"
    record_path = stem.with_suffix(".json")
    if not record_path.exists():
        blend = gltf_blend(glb, folder, args.timeout)
        script = str(BLENDER_SCRIPTS / "compare_truth.py")
        arguments = ["--disable-autoexec", str(blend), "--python", script, "--"]
        arguments += [str(stem), "--size", str(w), str(h)]
        arguments += ["--samples", str(args.samples)]
        arguments += ["--camera", args.camera] if args.camera else []
        line = blender_line(arguments, args.timeout, args.gpu)
        line |= {"file": str(glb), "key": key, "blend": str(blend)}
        record_path.write_text(json.dumps(line, indent=1))
    record = json.loads(record_path.read_text()) | {"kept": str(stem)}
    planes = dict(np.load(stem.with_suffix(".npz")))
    return planes, picture_of(stem.with_suffix(".png")), record


def reference_of(scene, glb, camera, size):
    """The reference's surface planes, the eye's view and its direct light by pass."""
    node = camera_node(scene, camera)
    flat = flatten(scene, MOST_TRIANGLES)
    seen = visibility(scene, node, size, flat)
    planes = surface(scene, node, size, "anisotropic", seen)
    tree = build({"positions": flat["positions"], "indices": flat["indices"]})
    tree = {k: np.ascontiguousarray(v) for k, v in tree.items()}
    lights, world, missing = described_lights(scene, glb.parent)
    eye = seen["camera"][0:3].astype(np.float64)
    ours = direct_light(planes, eye, tree, seen["diagonal"], lights, world)
    return planes, seen, ours, missing


def registered(planes, truth, diagonal):
    """Pixels where both sides see a surface at the same point; the share of those
    both see."""
    both = planes["covered"] & (truth["depth"] < BACKGROUND_DEPTH)
    distance = np.linalg.norm(planes["position"] - truth["position"], axis=-1)
    mask = both & (distance / diagonal <= REGISTERED)
    return mask, round(float(mask.sum() / max(both.sum(), 1)), 4)


def truth_passes(t):
    """The truth's planes by the comparison's passes (linear): the direct light passes
    as Cycles writes them (before their colour); direct with its colours; the diffuse
    indirect light with its colour."""
    lobes = ("diffuse", "glossy", "transmission")
    direct = sum(t[f"{lobe}_direct"] * t[f"{lobe}_color"] for lobe in lobes)
    indirect = t["diffuse_indirect"] * t["diffuse_color"]
    return {
        "base_colour": t["diffuse_color"] + t["glossy_color"],
        "diffuse": t["diffuse_direct"],
        "glossy": t["glossy_direct"],
        "specular": t["glossy_direct"] * t["glossy_color"],
        "indirect": indirect,
        "diffuse_direct": t["diffuse_direct"],
        "diffuse_colour": t["diffuse_color"],
        "direct": direct + t["emit"] + t["environment"],
    }


def by_pass(planes, ours, truth, mask, render, out):
    """Each pass on both sides: its numbers over the registered pixels, its strip
    (truth | reference | difference) as pass_<name>.png; the strips' cells."""
    ours_planes = {
        "base_colour": planes["base_color"],
        "diffuse": ours["diffuse_light"],
        "glossy": ours["glossy_light"],
        "specular": ours["specular"],
        "direct": ours["direct"],
    }
    numbers, rows = {}, []
    for name, mine in ours_planes.items():
        if name == "base_colour":
            show = to_srgb_standard8
            where = mask & (planes["metallic"] < METALLIC_UNDER)
        else:
            show = lambda x: displayed(x, render)[0]
            where = mask
        theirs = truth[name]
        a, b = show(mine), show(theirs)
        numbers[name] = pass_numbers(mine, theirs, a, b, where)
        if name == "base_colour":
            d = np.abs(mine[where] - theirs[where]).astype(np.float64)
            numbers[name]["mad"] = round(float(d.mean()), 4) if d.size else None
        cells = [(f"truth {name}", b), (f"reference {name}", a)]
        cells += [("|reference - truth|", heat(a, b, where))]
        strip(cells).save(out / f"pass_{name}.png")
        rows.append(cells)
    return numbers, rows


def indirect_pass(columns, truth, mask, render, out):
    """The indirect pass of each column ({label: the bounces' linear light}) against
    Cycles' diffuse indirect: numbers, strip, cells."""
    theirs = truth["indirect"]
    b = displayed(theirs, render)[0]
    numbers, cells, diffs = {}, [("truth indirect (diffuse)", b)], []
    for label, mine in columns.items():
        a = displayed(np.maximum(mine, 0.0), render)[0]
        numbers[label] = pass_numbers(mine, theirs, a, b, mask)
        cells.append((f"{label} indirect", a))
        diffs.append((f"|{label} - truth|", heat(a, b, mask)))
    strip(cells + diffs).save(out / "pass_indirect.png")
    return numbers, cells + diffs


def frame_direct(lit, truth, mask, render, out):
    """The frame's diffuse direct light (sun, lamps and the sky's own light, with the
    albedo) against Cycles' diffuse direct times its colour: numbers, strip, cells."""
    theirs = truth["diffuse_direct"] * truth["diffuse_colour"]
    a, b = displayed(lit, render)[0], displayed(theirs, render)[0]
    numbers = pass_numbers(lit, theirs, a, b, mask)
    cells = [("truth diffuse direct", b), ("frame direct (its lights)", a)]
    cells += [("|frame - truth|", heat(a, b, mask))]
    strip(cells).save(out / "pass_frame_direct.png")
    return numbers, cells


def earlier_card(args):
    """The card's pictures (whole, plain, off) and record of an earlier run's folder."""
    folder = args.card_from
    record = json.loads((folder / "numbers.json").read_text())["card"]
    stem = Path(record["picture"]).stem
    names = (record["picture"], f"{stem}_plain.png", record.get("off"))
    paths = [folder / n if isinstance(n, str) else None for n in names]
    pictures = [picture_of(p) if p is not None and p.exists() else None for p in paths]
    return *pictures, record | {"from": folder.name}


def card_picture(glb, name, args, out):
    """The card's last picture of --pipeline (bytes), the same under the plain tone and
    with the indirect switch off too (or None) and its run's record: a table scene by its
    name, else the file opened into a data root of the cache."""
    command = [sys.executable]
    environment = dict(os.environ)
    w, h = args.size
    if name is not None:
        target = out / f"card_{args.pipeline}.png"
        command += [str(HERE / "compare_card.py"), name, "--pipeline", args.pipeline]
        command += ["--size", str(w), str(h), "--frames", str(args.frames)]
        command += ["--card", str(args.card), "--out", str(target)]
        command += ["--off", INDIRECT, "--plain"]
    else:
        environment["PRISM_DATA"] = str(args.cache / "card_data")
        folder = out / "card"
        command += ["-m", "prism_cli", "open", str(glb), "--pipeline", args.pipeline]
        command += ["--size", str(w), str(h), "--frames", str(args.frames)]
        command += ["--card", str(args.card), "--bake", args.bake, "--out", str(folder)]
    command = ["timeout", str(args.card_timeout)] + command
    runner = os.environ.get(RUNNER_VARIABLE)
    if runner:
        command = [runner, str(args.card), "--"] + command
    lock = os.environ.get(LOCK_VARIABLE)
    if lock:
        command = [lock, "--wait", str(LOCK_WAIT), str(args.card), "--"] + command
    done = subprocess.run(
        command, capture_output=True, text=True, env=environment, check=False
    )
    lines = [ln for ln in done.stdout.splitlines() if ln.startswith("{")]
    record = json.loads(lines[-1]) if lines else {}
    record = {k: v for k, v in record.items() if k != "account"}
    record |= {"exit": done.returncode}
    if name is None:
        target = folder / record["picture"] if record.get("picture") else None
    if done.returncode or target is None or not target.exists():
        tail = (done.stdout + done.stderr).strip().splitlines()[-6:]
        return None, None, None, record | {"tail": tail}
    off = out / record["off"] if isinstance(record.get("off"), str) else None
    off = picture_of(off) if off is not None and off.exists() else None
    plain = target.with_name(f"{target.stem}_plain.png")
    plain = picture_of(plain) if plain.exists() else None
    return picture_of(target), plain, off, record


def crops(stem, args, size):
    """{name: pixel box} of the crops asked for: named ones of the scene, or given."""
    named = crops_of(stem, args.camera)
    out = {}
    for name in args.crop:
        if "=" in name:
            name, text = name.split("=", 1)
            fractions = tuple(float(v) for v in text.split(","))
        elif name == "all":
            for one, fractions in named.items():
                out[one] = crop_box(fractions, size)
            continue
        elif name in named:
            fractions = named[name]
        else:
            raise SystemExit(f"no crop {name!r} for {stem}; named: {sorted(named)}")
        out[name] = crop_box(fractions, size)
    return out


def main():
    """Compares one scene; writes the pictures and numbers.json, prints one line."""
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("scene", help="a .glb (sidecar beside it) or an opened scene")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--camera", default=None, help="a camera node; the render's")
    parser.add_argument("--size", type=int, nargs=2, default=(1280, 720))
    parser.add_argument("--samples", type=int, default=256)
    parser.add_argument("--cache", type=Path, default=None, help="the truths' folder")
    parser.add_argument(
        "--crop", nargs="*", default=[], help="NAME, all, N=x0,y0,x1,y1"
    )
    parser.add_argument("--no-reference", action="store_true")
    parser.add_argument(
        "--add", nargs="*", default=[], type=labelled_path, help="LABEL=PICTURE.png"
    )
    parser.add_argument("--card", type=int, default=None, help="draw on this card")
    parser.add_argument(
        "--card-from", type=Path, default=None, help="an earlier run's card pictures"
    )
    parser.add_argument("--pipeline", default="gi_threads")
    parser.add_argument("--frames", type=int, default=16)
    parser.add_argument("--bake", default="none", choices=("none", "wait"))
    parser.add_argument("--gpu", type=int, default=None, help="Cycles' CUDA device")
    parser.add_argument("--timeout", type=float, default=3600, help="a Blender run's")
    parser.add_argument("--card-timeout", type=int, default=1800)
    parser.add_argument("--data", type=Path, default=None)
    args = parser.parse_args()
    started = time.perf_counter()
    seconds = {}
    args.out.mkdir(parents=True, exist_ok=True)
    env_cache = os.environ.get(CACHE_VARIABLE)
    args.cache = args.cache or (Path(env_cache) if env_cache else args.out / "truth")
    glb, key, name = source_of(args.scene, args.data or data_root())
    stem = Path(scene_name(glb, key)).name.rsplit("_", 1)[0]
    size = tuple(args.size)
    record = {"scene": args.scene, "file": str(glb), "table_scene": name}
    record |= {"camera": args.camera, "size": list(size), "samples": args.samples}
    t, blender_picture, record["truth"] = truth_of(glb, key, args, args.cache)
    seconds["truth"] = round(time.perf_counter() - started, 1)
    scene = gltf.load(glb)
    truth = truth_passes(t)
    truth_shown, notes = displayed(t["combined"], scene.render)
    record["display"] = notes
    write_png(args.out / "truth.png", truth_shown)
    Image.fromarray(blender_picture).save(args.out / "truth_blender.png")
    cells = [("truth (Cycles, glTF)", truth_shown)]
    diffs, pictures, numbers, rows, mask, replaced = [], {}, {}, [], None, None
    indirect, whole = {}, {}
    if not args.no_reference:
        began = time.perf_counter()
        planes, seen, ours, missing = reference_of(scene, glb, args.camera, size)
        seconds["reference"] = round(time.perf_counter() - began, 1)
        mask, record["registered"] = registered(planes, t, seen["diagonal"])
        numbers, rows = by_pass(planes, ours, truth, mask, scene.render, args.out)
        shown = displayed(ours["direct"], scene.render)[0]
        write_png(args.out / "reference_direct.png", shown)
        record["not_carried"] = missing
        whole["reference_direct"] = whole_numbers(shown, truth_shown)
        label = "reference (direct light)"
        if name is not None:
            began = time.perf_counter()
            frame = frame_of(args.pipeline, name, size, args.data or data_root())
            seconds["frame"] = round(time.perf_counter() - began, 1)
            record["frame"] = {"tone": frame["tone"], "far_field": frame["far_field"]}
            record["lights"] = {"reference_frame": frame["lights"], "passes": "file"}
            shown = frame["display"]
            label = f"reference ({args.pipeline}'s frame)"
            if frame["bounces"] is not None:
                indirect["reference"] = frame["bounces"]
                replaced = frame["off"] - frame["direct"] - frame["sky"]
                lit = frame["lit"] + frame["sky"]
                numbers["frame_direct"], cells_lit = frame_direct(
                    lit, truth, mask, scene.render, args.out
                )
                rows.append(cells_lit)
            write_png(args.out / "reference_frame.png", shown)
        whole["reference"] = whole_numbers(shown, truth_shown)
        write_png(args.out / "reference.png", shown)
        cells.append((label, shown))
        diffs.append(("|reference - truth|", heat(shown, truth_shown)))
        pictures["reference"] = shown
    given = [(label, picture_of(Path(path))) for label, path in args.add]
    if args.card is not None or args.card_from is not None:
        began = time.perf_counter()
        if args.card_from is None:
            card, card_plain, card_off, record["card"] = card_picture(
                glb, name, args, args.out
            )
        else:
            card, card_plain, card_off, record["card"] = earlier_card(args)
        seconds["card"] = round(time.perf_counter() - began, 1)
        given += [] if card is None else [("card", card)]
        tone = record["card"].get("tone")
        on = card_linear(card if card_plain is None else card_plain, tone)
        off = card_linear(card_off, tone)
        if on is not None and off is not None and replaced is not None:
            indirect["card"] = on - off + replaced
            record["lights"]["card"] = frame["lights"]
    for label, picture in given:
        if picture.shape[:2] != truth_shown.shape[:2]:
            record.setdefault("size_differs", {})[label] = list(picture.shape[:2])
            continue
        whole[label] = whole_numbers(picture, truth_shown)
        whole[f"{label}_vs_blender_display"] = display_numbers(picture, blender_picture)
        title = f"card ({args.pipeline})" if label == "card" else label
        cells.append((title, picture))
        diffs.append((f"|{label} - truth|", heat(picture, truth_shown)))
        pictures[label] = picture
    numbers["whole"] = whole
    indirect = {k: v for k, v in indirect.items() if v.shape == truth_shown.shape}
    if indirect:
        where = mask if mask is not None else np.ones(size[::-1], bool)
        numbers["indirect"], cells_indirect = indirect_pass(
            indirect, truth, where, scene.render, args.out
        )
        rows.insert(0, cells_indirect)
    sheet([cells + diffs] + rows).save(args.out / "strip.png")
    record["crops"] = {}
    for crop, box in crops(stem, args, size).items():
        all_cells = [(label, cropped(p, box)) for label, p in cells + diffs]
        strip(all_cells).save(args.out / f"crop_{crop}.png")
        entry = {"box": list(box)}
        for column, picture in pictures.items():
            entry[column] = whole_numbers(picture, truth_shown, box)
        record["crops"][crop] = entry
    record["numbers"] = numbers
    record["seconds"] = seconds | {"all": round(time.perf_counter() - started, 1)}
    (args.out / "numbers.json").write_text(json.dumps(record, indent=1))
    print(json.dumps(record), flush=True)
    asked = args.card is not None or args.card_from is not None
    raise SystemExit(1 if asked and "card" not in pictures else 0)


if __name__ == "__main__":
    main()
