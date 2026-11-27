"""The whole picture's error of a `compare.py` run ranked by cause: pixel classes (first
hit transmissive by material with its causes, emitters first hit opaque) and terms
(lights, indirect, textures, specular, specular not carried, display); a table and one
JSON line (no card). `compare_rank.py RUN [--data D] [--pipeline P] [--carried-from G]`
"""

import argparse
import json
from pathlib import Path

import numpy as np
from compare import reference_of, registered
from compare_frame import frame_of
from compare_index import checked
from PIL import Image

from prism_common.paths import data_root
from prism_reference.post.display import GAMMA
from prism_reference.scene.importers import gltf

NOT_CARRIED = ("KHR_materials_anisotropy", "KHR_materials_clearcoat")
TRANSMISSIVE = "KHR_materials_transmission"
SHARE_OF_TRUTH = 0.5  # a pass over this share of the truth's colour names the pixel
LAST_BYTE = 254.5 / 255  # Blender's picture is inverted below it
CLASS = "first hit transmissive"


def loaded(run):
    """The run's record, the truth's planes (linear) and Blender's picture (0 to 1);
    SystemExit when the kept truth is not of the run's .glb."""
    record = json.loads((run / "numbers.json").read_text())
    stem = Path(record["truth"]["kept"])
    checked(stem.parent.parent, stem, Path(record["file"]))
    planes = {
        k: v.astype(np.float64) for k, v in np.load(stem.with_suffix(".npz")).items()
    }
    picture = Image.open(stem.with_suffix(".png")).convert("RGB")
    return record, planes, np.asarray(picture).astype(np.float64) / 255


def odd_materials(scene, ids, carried_from):
    """The material ids whose extensions the frame does not carry (by name in
    `carried_from`, another export of the scene, when given)."""
    source = gltf.load(carried_from) if carried_from is not None else scene
    names = {
        m.name for m in source.materials if any(k in m.carried for k in NOT_CARRIED)
    }
    return {m for m in ids if scene.materials[m].name in names}


def classes(scene, planes, truth, mask, error):
    """{row: (pixels, error sum)} of the pixel classes and the first hit transmissive
    and emitters masks."""
    material = planes["material"]
    ids = np.unique(material[material >= 0])
    transmissive = [
        m
        for m in ids
        if TRANSMISSIVE in scene.materials[m].carried
        or getattr(scene.materials[m], "alpha_mode", "") == "BLEND"
    ]
    colour = truth["combined"].mean(-1)
    glow = planes["emissive"].max(-1) > 0
    environment = np.zeros_like(colour, dtype=bool)
    if "emit" in truth:
        glow |= truth["emit"].mean(-1) > SHARE_OF_TRUTH * colour
    if "environment" in truth:
        environment = truth["environment"].mean(-1) > SHARE_OF_TRUTH * colour
    first = mask & np.isin(material, transmissive)
    rows, causes = {}, {}
    for m in np.unique(material[first]):
        where = first & (material == m)
        name = f"{CLASS}: {scene.materials[m].name}"
        rows[name] = (int(where.sum()), float(error[where].sum()))
        if "emit" in truth or "environment" in truth:
            parts = {
                "emission": where & glow,
                "environment": where & ~glow & environment,
            }
            parts["surface behind"] = where & ~glow & ~environment
            causes[name] = {k: float(error[w].sum()) for k, w in parts.items()}
    shining = np.zeros_like(colour)
    for name in ("emit", "environment"):
        shining = shining + (truth[name].mean(-1) if name in truth else 0)
    emitters = mask & ~first & (glow | (shining > SHARE_OF_TRUTH * colour))
    rows["emitters, window, picture (first hit opaque)"] = (
        int(emitters.sum()),
        float(error[emitters].sum()),
    )
    return rows, causes, first | emitters


def terms(frame, ours, planes, truth, blender, odd, rest):
    """{row: (pixels, error sum)} of the terms over the `rest` pixels."""
    colour = frame["colour"]
    lit = frame["lit"] + (frame["sky"] if frame["sky"] is not None else 0)
    bounces = frame["bounces"] if frame["bounces"] is not None else 0 * colour
    specular = colour - lit - bounces
    emissive = np.where(planes["covered"][..., None], planes["emissive"], 0)
    diffuse = ours["direct"] - ours["specular"] - ours["sheen"] - emissive
    t = truth
    cycles_diffuse = t["diffuse_direct"] * t["diffuse_color"]
    glossy = (t["glossy_direct"] + t["glossy_indirect"]) * t["glossy_color"]
    transmission = t["transmission_direct"] + t["transmission_indirect"]
    indirect = t["diffuse_indirect"] * t["diffuse_color"]
    indirect = indirect + transmission * t["transmission_color"]
    shown = np.minimum(blender**GAMMA, LAST_BYTE)
    display = shown / (1 - shown) / frame["tone"]["exposure"]
    is_odd = np.isin(planes["material"], list(odd))[..., None]
    out = {
        "lights": (rest, np.abs(lit - diffuse)),
        "indirect": (rest, np.abs(bounces - indirect)),
        "textures": (rest, np.abs(diffuse - cycles_diffuse)),
        "specular": (rest & ~is_odd[..., 0], np.where(is_odd, 0, specular - glossy)),
        "specular not carried": (
            rest & is_odd[..., 0],
            np.where(is_odd, specular - glossy, 0),
        ),
        "display": (rest, np.abs(display - t["combined"])),
    }
    return {
        k: (int(w.sum()), float(np.abs(v).mean(-1)[rest].sum()))
        for k, (w, v) in out.items()
    }


def ranked(run, data, pipeline, carried_from):
    """The run's ranking: {scene, registered, error sum, rows, causes}."""
    record, truth, blender = loaded(run)
    glb, name = Path(record["file"]), record["table_scene"]
    if name is None:
        raise SystemExit(f"{run}: not a table scene; the frame's terms need one")
    size = tuple(record["size"])
    scene = gltf.load(glb)
    planes, seen, ours, _ = reference_of(scene, glb, record["camera"], size)
    mask, share = registered(planes, truth, seen["diagonal"])
    frame = frame_of(pipeline, name, size, data)
    error = np.abs(frame["colour"] - truth["combined"]).mean(-1)
    rows, causes, taken = classes(scene, planes, truth, mask, error)
    material = planes["material"]
    odd = odd_materials(scene, np.unique(material[material >= 0]), carried_from)
    rows |= terms(frame, ours, planes, truth, blender, odd, mask & ~taken)
    total = sum(s for _, s in rows.values())
    shares = {
        k: {"pixels": p, "share": round(s / total, 3)} for k, (p, s) in rows.items()
    }
    out = {"scene": record["scene"], "pipeline": pipeline, "registered": share}
    out |= {"error_sum": round(float(error[mask].sum()), 1)}
    causes = {
        row: {k: round(v / total, 3) for k, v in parts.items()}
        for row, parts in causes.items()
    }
    return out | {"rows": shares, "causes": causes}


def table(rank):
    """The ranking as a Markdown table, largest share first."""
    lines = ["| cause | pixels | share |", "| --- | --- | --- |"]
    rows = sorted(rank["rows"].items(), key=lambda kv: -kv[1]["share"])
    for name, row in rows:
        causes = rank["causes"].get(name)
        note = (
            ""
            if not causes
            else " (" + ", ".join(f"{k} {v}" for k, v in causes.items()) + ")"
        )
        lines.append(f"| {name}{note} | {row['pixels']} | {row['share']:.3f} |")
    return "\n".join(lines)


def main():
    """Ranks one run folder; writes rank.md there, prints the table and one JSON line."""
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("run", type=Path, help="a folder compare.py wrote")
    parser.add_argument("--data", type=Path, default=None)
    parser.add_argument(
        "--pipeline", default=None, help="the run's card's, else gi_threads"
    )
    parser.add_argument(
        "--carried-from", type=Path, default=None, help="another export of the scene"
    )
    args = parser.parse_args()
    record = json.loads((args.run / "numbers.json").read_text())
    pipeline = args.pipeline or (record.get("card") or {}).get("pipeline", "gi_threads")
    rank = ranked(args.run, args.data or data_root(), pipeline, args.carried_from)
    text = table(rank)
    (args.run / "rank.md").write_text(text + "\n")
    print(text, flush=True)
    print(json.dumps(rank), flush=True)


if __name__ == "__main__":
    main()
