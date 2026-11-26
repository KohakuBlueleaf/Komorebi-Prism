"""The reference's direct light of an artist's scene against Cycles' direct-light passes
of the same scene: passes (Blender) | compare | table; pictures and compare.json under
<data>/artist/<key>/light/, a copy and a README table under measurements/ (no card)."""

import argparse
import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from prism_common.paths import data_root
from prism_reference.direct.described.direct import (
    KINDS,
    described_lights,
    direct_light,
)
from prism_reference.direct.described.sample import AREA_SAMPLES, WORLD_SAMPLES
from prism_reference.io.pictures import colormap
from prism_reference.io.png import write_png
from prism_reference.material.surface import (
    MOST_TRIANGLES,
    is_transparent,
    surface,
    visibility,
)
from prism_reference.post.described import displayed
from prism_reference.post.display import to_srgb_standard8
from prism_reference.scene.artist.entry import camera_node
from prism_reference.scene.artist.table import artist_dir, blend_path
from prism_reference.scene.description.flatten import drawn_triangles, flatten
from prism_reference.scene.importers import gltf
from prism_reference.trace.tree import build

BLENDER_VARIABLE = "PRISM_BLENDER"
SCRIPT = Path(__file__).resolve().parent.parent / "blender" / "light_passes.py"
MEASURED = Path(__file__).resolve().parents[2] / "measurements" / "reference_light"
SCENE_FILES = ("scene.glb", "scene.prism.json", "scene.instances.npz")
BACKGROUND_DEPTH = (
    1e9  # surface_compare's rule: Cycles' depth at or past it is no surface
)
REGISTERED = 1e-3  # surface_compare's rule: positions within this share of the diagonal
FLOOR = 1e-3  # the relative difference's floor, by the median of Cycles' picture
PASSES = (("diffuse", "diffuse_light", "diffuse_direct"),)
PASSES += (("glossy", "glossy_light", "glossy_direct"),)
RUNS = ("all", *KINDS, "none")
BLENDER_KIND = {"POINT": "point", "SPOT": "spot", "SUN": "sun", "AREA": "area"}
VISIBILITY = (
    ("render_hidden", "objects in the description but hidden in Cycles' render"),
    ("no_shadow", "objects casting no shadow in Cycles"),
)
LONG_SIDE = 1280  # Cycles' passes: the sidecar's render size scaled to this long side
PICTURE_QUANTILE = 99  # the pictures' white: this percentile of Cycles' picture


def passes_size(key, data):
    """The sidecar's render size scaled to a long side of LONG_SIDE."""
    sidecar = json.loads((artist_dir(data) / key / "scene.prism.json").read_text())
    width, height = sidecar["render"]["size"]
    scale = LONG_SIDE / max(width, height)
    return round(width * scale), round(height * scale)


def run_passes(key, data, size, samples, timeout, runs=None):
    """Runs light_passes.py on the scene's .blend at `size` (None: `passes_size`); its
    JSON line, or the failure."""
    folder = artist_dir(data) / key / "light"
    size = size or passes_size(key, data)
    command = [
        os.environ.get(BLENDER_VARIABLE, "blender"),
        "--background",
        "--disable-autoexec",
        str(blend_path(key, data)),
        "--python",
        str(SCRIPT),
        "--",
        str(folder),
        "--size",
        *map(str, size),
        "--samples",
        str(samples),
        *([] if runs is None else ["--runs", *runs]),
    ]
    try:
        done = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired:
        return {"scene": key, "error": f"stopped after {timeout} s"}
    lines = [ln[ln.find('{"') :] for ln in done.stdout.splitlines() if '{"' in ln]
    if done.returncode or not lines:
        tail = (done.stdout + done.stderr).strip().splitlines()[-5:]
        return {"scene": key, "error": f"exit {done.returncode}", "tail": tail}
    return {"scene": key} | json.loads(lines[-1])


def modified(folder, names):
    """{file name: modification time (UTC, ISO)} of the files that exist."""
    out = {}
    for name in names:
        path = folder / name
        if path.exists():
            stamp = datetime.fromtimestamp(path.stat().st_mtime, UTC)
            out[name] = stamp.isoformat(timespec="seconds")
    return out


def registration(planes, cyc, diagonal):
    """surface_compare's rule: both sides see a surface and the positions lie within
    REGISTERED of the diagonal; the mask and its numbers."""
    both = planes["covered"] & (cyc["depth"] < BACKGROUND_DEPTH)
    distance = np.linalg.norm(planes["position"] - cyc["position"], axis=-1)
    distance = np.where(both, distance / diagonal, 0.0)
    mask = both & (distance <= REGISTERED)
    return mask, {
        "registered": float(mask.sum() / max(both.sum(), 1)),
        "pixels": int(mask.sum()),
        "one_side_only": float(
            np.mean(planes["covered"] != (cyc["depth"] < BACKGROUND_DEPTH))
        ),
    }


def numbers(ours, theirs, mask):
    """Median and p90 of |ours - theirs| / (|theirs| + FLOOR x median |theirs|) on the
    grey (channel mean) over the mask, and the ratio of the two means."""
    o = ours[mask].astype(np.float64).mean(axis=-1)
    t = theirs[mask].astype(np.float64).mean(axis=-1)
    if not len(t):
        return {"pixels": 0}
    floor = FLOOR * float(np.median(np.abs(t)))
    if floor <= 0:
        floor = FLOOR * float(np.mean(np.abs(t)))
    rel = np.abs(o - t) / np.maximum(np.abs(t) + floor, 1e-30)
    mean_t = float(np.mean(t))
    return {
        "median": float(np.median(rel)),
        "p90": float(np.percentile(rel, 90)),
        "ratio_of_means": float(np.mean(o)) / mean_t if mean_t > 0 else None,
        "mean_ours": float(np.mean(o)),
        "mean_cycles": mean_t,
        "pixels": len(t),
    }


def panel(ours, theirs, mask, covered):
    """Ours, Cycles and the relative difference side by side (bytes)."""
    seen = theirs[covered].mean(axis=-1) if covered.any() else np.zeros(1)
    white = float(np.percentile(seen, PICTURE_QUANTILE)) if seen.size else 1.0
    white = white if white > 0 else max(float(ours.max()), 1e-30)
    left = to_srgb_standard8(np.where(covered[..., None], ours / white, 0.0))
    middle = to_srgb_standard8(theirs / white)
    t, o = theirs.mean(axis=-1), ours.mean(axis=-1)
    floor = FLOOR * float(np.median(np.abs(t[mask]))) if mask.any() else 0.0
    rel = np.abs(o - t) / np.maximum(np.abs(t) + floor, 1e-30)
    right = np.where(mask[..., None], colormap(rel, 0.0, 1.0), 0).astype(np.uint8)
    return np.concatenate([left, middle, right], axis=1)


def runs_of(folder):
    """The runs rendered under the folder, in RUNS' order."""
    return [r for r in RUNS if (folder / f"cycles_{r}.npz").exists()]


def ours_of(ours, run, shape):
    """Our planes of one run: every light, one kind, or zeros (nothing to compare)."""
    if run == "all":
        return ours
    zero = {name: np.zeros(shape, np.float32) for _, name, _ in PASSES}
    return ours["kinds"].get(run, zero)


def counted(kinds):
    """{kind: count} of a list of kinds."""
    return {k: kinds.count(k) for k in KINDS if kinds.count(k)}


def node_factor(nodes):
    """What a light's own nodes add in Cycles beside its power and colour, or ""."""
    if not nodes or not nodes.get("emission"):
        return ""
    parts = []
    strength = nodes.get("strength")
    if strength is None and "falloff_strength" not in nodes:
        parts.append("strength from a link")
    elif strength is not None and strength != 1.0:
        parts.append(f"strength x{strength:g}")
    if nodes.get("falloff_strength", 1.0) != 1.0:
        parts.append(f"falloff strength {nodes['falloff_strength']:g}")
    if nodes.get("color_linked"):
        parts.append("colour from nodes")
    return " ".join(parts)


def grouped(lines):
    """Lines "<what> (<name>)" said once each as "<what>: <count>", in their first
    order; a line without a name as it is."""
    whats = [line.rsplit(" (", 1)[0] if line.endswith(")") else line for line in lines]
    named = [w for w, line in zip(whats, lines, strict=True) if w != line]
    return [f"{w}: {named.count(w)}" if w in named else w for w in dict.fromkeys(whats)]


def not_carried(scene, missing, notes, blender, runs, counts):
    """What the reference does not carry of this scene, one line each."""
    out = grouped(missing) + list(notes)
    dropped = [n.what for n in scene.notes if n.kind == "dropped"]
    out += [
        f"{what} (the description): {dropped.count(what)}"
        for what in sorted(set(dropped))
    ]
    lights = blender.get("lights", [])
    reference = {k: n for k, n in counts["reference"].items() if k != "world"}
    counted_blender = counts["blender"]
    trees = [d for d in lights if node_factor(d.get("nodes"))]
    if trees:
        factors = sorted({node_factor(d["nodes"]) for d in trees})
        out.append(f"light node trees: {len(trees)} lights ({', '.join(factors)})")
    soft = [d["name"] for d in lights if d.get("radius", 0) > 0]
    if soft:
        out.append(f"point and spot radius (soft shadows): {len(soft)} lights")
    spots = [d for d in lights if d["type"] == "SPOT"]
    if spots:
        out.append(f"spot blend: glTF's cone in place of Cycles' ({len(spots)} spots)")
    suns = [d["name"] for d in lights if d.get("angle", 0) > 0]
    if suns:
        out.append(f"sun angle (soft shadows): {len(suns)} lights")
    spread = [d["name"] for d in lights if d.get("spread", np.pi) < np.pi - 1e-6]
    if spread:
        out.append(f"area spread under 180 degrees: {len(spread)} lights")
    portals = [d["name"] for d in lights if d.get("is_portal")]
    if portals:
        out.append(f"portals drawn as area lights: {len(portals)}")
    if any(not d.get("normalize", True) for d in lights):
        out.append("lights not normalized by their size")
    if any(not d.get("cast_shadow", True) for d in lights):
        out.append("lights casting no shadow")
    alpha = [m.name for m in scene.materials if m.alpha_mode == "MASK"]
    alpha += [m.name for m in scene.materials if is_transparent(m)]
    if alpha:
        out.append(
            f"shadows of masked, blended or transmitting surfaces opaque: {len(alpha)}"
            " materials"
        )
    seen = blender.get("visibility", {})
    for field, what in VISIBILITY:
        if seen.get(field, {}).get("count"):
            entry = seen[field]
            out.append(f"{what}: {entry['count']}")
    if any(seen.get("camera_shift", [0, 0])):
        out.append(
            f"camera shift {seen['camera_shift']} (the surface's camera has none)"
        )
    if reference != counted_blender:
        out.append(
            f"lights by kind differ: reference {reference}, Blender {counted_blender}"
        )
    none = runs.get("none", {}).get("diffuse", {}).get("mean_cycles") or 0.0
    if none > 0:
        out.append("emitting surfaces as lights (Cycles' run with no light: 'none')")
    return out


def compare(key, data, filter_name="anisotropic"):
    """Writes the pictures and compare.json of one scene; returns compare.json's dict."""
    seconds, last = {}, [time.perf_counter()]

    def step(name):
        now = time.perf_counter()
        seconds[name], last[0] = round(now - last[0], 2), now

    scene_folder = artist_dir(data) / key
    folder = scene_folder / "light"
    cyc_all = dict(np.load(folder / "cycles_all.npz"))
    size = tuple(int(n) for n in cyc_all["size"])
    record = {
        "scene": key,
        "size": list(size),
        "files": modified(scene_folder, SCENE_FILES),
    }
    scene = gltf.load(scene_folder / "scene.glb")
    after = modified(scene_folder, SCENE_FILES)
    if after != record["files"]:
        record["files_changed_while_read"] = after
    record["triangles"] = {"drawn": drawn_triangles(scene), "budget": MOST_TRIANGLES}
    node = camera_node(scene)
    step("load")
    flat = flatten(scene, MOST_TRIANGLES)
    seen = visibility(scene, node, size, flat)
    planes = surface(scene, node, size, filter_name, seen)
    step("surface")
    tree = build({"positions": flat["positions"], "indices": flat["indices"]})
    tree = {k: np.ascontiguousarray(v) for k, v in tree.items()}
    step("tree")
    lights, world, missing = described_lights(scene, scene_folder)
    eye = seen["camera"][0:3].astype(np.float64)
    ours = direct_light(planes, eye, tree, seen["diagonal"], lights, world)
    step("direct light")
    record["samples"] = {"area": AREA_SAMPLES, "world": WORLD_SAMPLES}
    record["rays"] = ours["rays"]
    mask, record["registration"] = registration(planes, cyc_all, seen["diagonal"])
    shape = planes["covered"].shape + (3,)
    record["runs"], pictures = {}, []
    runs = runs_of(folder)
    surfaces = dict(np.load(folder / "cycles_none.npz")) if "none" in runs else None
    for run in runs:
        cyc = cyc_all if run == "all" else dict(np.load(folder / f"cycles_{run}.npz"))
        mine = ours_of(ours, run, shape)
        entry = {}
        for label, plane, cycles_plane in PASSES:
            theirs = cyc[cycles_plane]
            if surfaces is not None and run != "none":
                theirs = theirs - surfaces[cycles_plane]
            entry[label] = numbers(mine[plane], theirs, mask)
            name = f"{run}_{label}.png"
            image = panel(mine[plane], theirs, mask, planes["covered"])
            write_png(folder / name, image)
            pictures.append(name)
        record["runs"][run] = entry
    picture, notes = displayed(ours["direct"], scene.render)
    theirs, _ = displayed(cyc_all["combined"], scene.render)
    write_png(folder / "direct.png", np.concatenate([picture, theirs], axis=1))
    pictures.append("direct.png")
    step("compare")
    blender_file = folder / "blender_lights.json"
    blender = json.loads(blender_file.read_text()) if blender_file.exists() else {}
    record["lights"] = {
        "reference": counted(
            [light["kind"] for light in lights] + ["world"] * bool(world)
        ),
        "blender": counted(
            [BLENDER_KIND.get(d["type"], d["type"]) for d in blender.get("lights", [])]
        ),
        "cycles_samples": blender.get("samples"),
    }
    record["not_carried"] = not_carried(
        scene, missing, notes, blender, record["runs"], record["lights"]
    )
    record["pictures"] = pictures
    record["seconds"] = seconds
    (folder / "compare.json").write_text(json.dumps(record, indent=1))
    MEASURED.mkdir(parents=True, exist_ok=True)
    (MEASURED / f"{key}.json").write_text(json.dumps(record, indent=1) + "\n")
    return record


def cell(entry, field):
    """A table cell of a number of `numbers`."""
    value = entry.get(field)
    return "-" if value is None else f"{value:.3f}"


def table():
    """Writes measurements/reference_light/README.md from the records there."""
    records = [json.loads(p.read_text()) for p in sorted(MEASURED.glob("*.json"))]
    lines = [
        "# The reference's direct light against Cycles",
        "",
        "`python scripts/run/light_compare.py passes|compare <scene ...>` then `table`;",
        "the method is in",
        "[described light](../../docs/internals/reference/described_light.md). A row is",
        "one run: every light (`all`), one light kind with the others off on both sides,",
        "or none (`none`: Cycles' light from emitting surfaces, the reference 0). Every",
        "other run's Cycles passes have the run `none` taken off: the surfaces'",
        "emission cannot be switched off in Blender as a light is. Over the",
        "registered pixels: the median and the 90th percentile of",
        "|ours - Cycles| / (|Cycles| + 1e-3 x median |Cycles|) on the channel mean, and",
        "the ratio of the means (ours / Cycles).",
        "",
        (
            "| scene | run | diffuse median | diffuse p90 | diffuse ratio "
            "| glossy median | glossy p90 | glossy ratio |"
        ),
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in records:
        for run, entry in r["runs"].items():
            d, g = entry["diffuse"], entry["glossy"]
            lines.append(
                f"| {r['scene']} | {run} | {cell(d, 'median')} | {cell(d, 'p90')} "
                f"| {cell(d, 'ratio_of_means')} | {cell(g, 'median')} "
                f"| {cell(g, 'p90')} | {cell(g, 'ratio_of_means')} |"
            )
    lines += ["", "## The lights and what is not carried", ""]
    for r in records:
        reference = ", ".join(f"{k} {n}" for k, n in r["lights"]["reference"].items())
        blender = ", ".join(f"{k} {n}" for k, n in r["lights"]["blender"].items())
        lines.append(f"**{r['scene']}** ({r['size'][0]} x {r['size'][1]}, Cycles")
        lines.append(f"{r['lights']['cycles_samples']} samples, registered")
        lines.append(f"{r['registration']['registered']:.3f}): reference {reference};")
        lines.append(f"Blender {blender}.")
        lines.append("")
        lines += [f"- {line}" for line in r["not_carried"]] or ["- nothing listed"]
        lines.append("")
    (MEASURED / "README.md").write_text("\n".join(lines))


def main():
    """Renders Cycles' passes, compares, or writes the table; one JSON line a scene."""
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("command", choices=("passes", "compare", "table"))
    parser.add_argument("scenes", nargs="*")
    parser.add_argument("--data", type=Path, default=None)
    parser.add_argument("--size", type=int, nargs=2, default=None)
    parser.add_argument("--samples", type=int, default=256)
    parser.add_argument("--timeout", type=float, default=None, help="seconds a run")
    parser.add_argument("--runs", nargs="*", default=None, help="passes: these only")
    args = parser.parse_args()
    data = args.data or data_root()
    if args.command == "table":
        table()
        return
    for key in args.scenes:
        if args.command == "passes":
            size, samples = args.size and tuple(args.size), args.samples
            line = run_passes(key, data, size, samples, args.timeout, args.runs)
        else:
            record = compare(key, data)
            line = {k: v for k, v in record.items() if k != "pictures"}
        print(json.dumps(line), flush=True)


if __name__ == "__main__":
    main()
