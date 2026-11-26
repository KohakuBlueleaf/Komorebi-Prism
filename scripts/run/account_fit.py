"""Per-item constants from the account's records (measurements/account): for SHADE,
LIGHT and SHOW, a least-squares fit of a core's busy cycles against its items, its rows
and its fetched pages (three constants, cycles each), with the fit's relative residual
(RMS over cores), a pipeline's scene and all its scenes together; written to
measurements/account/fit.json. Example: python scripts/run/account_fit.py
"""

import argparse
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / "measurements" / "account"
# a stage's command, the CPU whose busy steps are fitted, its counts: items, rows and
# the pages it fetched (summed)
STAGES = {
    "SHADE": ("shade", "pack", "tiles", "rows", ("pages",)),
    "LIGHT": ("light", "pack", "tiles", "rows", ("pages", "field_pages")),
    "SHOW": ("show", "writer", "items", "rows", ()),
}
TERMS = ("items", "rows", "pages")


def parse():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--folder", type=Path, default=FOLDER)
    parser.add_argument("--out", type=Path, default=None)
    return parser.parse_args()


def points(record, stage):
    """(busy cycles, [items, rows, pages]) a core of each of the record's commands of
    `stage` (each layer's SHADE its own)."""
    command, cpu, items, rows, pages = STAGES[stage]
    mhz = record["case"]["aiclk_mhz"][0]
    busy, counts = [], []
    for one in record["stages"]:
        if one["command"] != command or not one.get("cores"):
            continue
        steps = one["cores"][cpu]["busy"].values()
        busy.append(np.sum([np.asarray(s) for s in steps], axis=0) * mhz * 1e3)
        got = one["items"]
        fetched = sum((np.asarray(got[p]) for p in pages), np.zeros(len(busy[-1])))
        counts.append(np.stack([got[items], got[rows], fetched], axis=1))
    if not busy:
        return np.zeros(0), np.zeros((0, 3))
    return np.concatenate(busy), np.concatenate(counts)


def fitted(busy, counts):
    """The three constants (cycles an item, a row, a page), the relative residual RMS
    over the cores with work, and the cores fitted."""
    keep = busy > 0
    busy, counts = busy[keep], counts[keep]
    if not len(busy):
        return None
    constants = np.linalg.lstsq(counts, busy, rcond=None)[0]
    residual = (counts @ constants - busy) / busy
    return {
        "constants": {t: round(float(c), 3) for t, c in zip(TERMS, constants)},
        "residual": round(float(np.sqrt(np.mean(residual**2))), 4),
        "cores": len(busy),
    }


def main():
    args = parse()
    records = [
        json.loads(path.read_text()) for path in sorted(args.folder.glob("*_*.json"))
    ]
    records = [r for r in records if "stages" in r]
    out = {}
    for pipeline in sorted({r["case"]["pipeline"] for r in records}):
        own = [r for r in records if r["case"]["pipeline"] == pipeline]
        for stage in STAGES:
            by_scene = {}
            for record in own:
                busy, counts = points(record, stage)
                scene = record["case"]["scene"]
                was = by_scene.get(scene, (np.zeros(0), np.zeros((0, 3))))
                by_scene[scene] = (
                    np.concatenate([was[0], busy]),
                    np.concatenate([was[1], counts]),
                )
            every = (
                np.concatenate([b for b, _ in by_scene.values()]),
                np.concatenate([c for _, c in by_scene.values()]),
            )
            out[f"{pipeline}.{stage}"] = {
                "all": fitted(*every),
                "scenes": {s: fitted(*pair) for s, pair in sorted(by_scene.items())},
            }
    path = args.out or args.folder / "fit.json"
    path.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: v["all"] for k, v in out.items()}), flush=True)


if __name__ == "__main__":
    main()
