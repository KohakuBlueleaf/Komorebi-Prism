"""Each case's tables written by `scripts/blender/view.py` from the Blender named by
$PRISM_BLENDER, a test picture (ramps over 24 stops of grey and eight hues, random HDR
colours) and the given linear frames through Blender's view transform (its 8-bit save
and OpenColorIO's values) and through the reference's; exit 1 past 1 in 8 bits."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

from prism_common.paths import cache_root
from prism_reference.post.view import load_view, view8

BLENDER_VARIABLE = "PRISM_BLENDER"
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "blender" / "view.py"
CASES = (
    ("AgX", "None"),
    ("Filmic", "None"),
    ("Filmic", "High Contrast"),
    ("Filmic", "Medium High Contrast"),
    ("Standard", "None"),
    ("AgX", "AgX - Punchy"),
)
STOPS = (-14.0, 10.0)  # the ramps' exposures, log2
HUES = ((1, 1, 1), (1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 0), (0, 1, 1), (1, 0, 1))
HUES += ((1, 0.5, 0.2), (0.2, 0.5, 1))
RAMP, RANDOM_ROWS, WIDTH = 4096, 256, 1024
MOST = 1  # the largest difference allowed, in 8 bits
TIMEOUT_S = 600


def test_picture(seed=1):
    """(H, 1024, 3) float32: the hues' ramps, then rows of random HDR colours."""
    exposure = 2.0 ** np.linspace(*STOPS, RAMP)
    ramps = (exposure[None, :, None] * np.array(HUES)[:, None, :]).reshape(-1, 3)
    rng = np.random.default_rng(seed)
    count = RANDOM_ROWS * WIDTH
    scale = 2.0 ** rng.uniform(STOPS[0] + 2, STOPS[1] - 2, (count, 1))
    random = rng.random((count, 3)) * scale
    return np.concatenate([ramps, random]).reshape(-1, WIDTH, 3).astype(np.float32)


def blender(*arguments):
    """Runs view.py in Blender; its JSON line."""
    command = [os.environ.get(BLENDER_VARIABLE, "blender"), "--background"]
    command += ["--factory-startup", "--python", str(SCRIPT), "--", *arguments]
    done = subprocess.run(
        command, check=False, capture_output=True, text=True, timeout=TIMEOUT_S
    )
    lines = [line for line in done.stdout.splitlines() if line.startswith("{")]
    if done.returncode != 0 or not lines:
        raise RuntimeError(f"view.py {arguments[0]} failed:\n{done.stderr[-2000:]}")
    return json.loads(lines[-1])


def differences(ours, theirs):
    """The largest difference, and the share of channels that differ."""
    d = np.abs(ours.astype(np.int16) - theirs.astype(np.int16))
    return int(d.max()), float(np.mean(d > 0))


def case(view, look, pictures, folder):
    """A case's record: per picture, ours against Blender's save and OpenColorIO's."""
    stem = f"{view}_{look}".replace(" ", "_")
    tables = folder / f"{stem}.view.npz"
    written = blender("tables", str(tables), view, look)
    record = {"view": view, "look": look, "notes": written["notes"]}
    if written["view_tables"] is None:
        return record | {"tables": None}
    ops, kept = load_view(tables)
    record["kinds"] = [kind for kind, _ in ops]
    for name, source in pictures.items():
        out = folder / f"{stem}_{name}"
        out.mkdir(exist_ok=True)
        blender("pictures", str(source), str(out), kept["view"], kept["look"] or "None")
        ours = view8(ops, np.load(source))
        saved = np.load(out / "blender.npy")
        theirs = np.rint(np.clip(np.load(out / "ocio.npy"), 0, 1) * 255).astype("u1")
        record[name] = {
            "blender": differences(ours, saved),
            "ocio": differences(ours, theirs),
        }
    return record


def main():
    """The cases, each with the test picture and the frames given."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--frame", action="append", default=[])
    args = parser.parse_args()
    folder = cache_root() / "view_transform"
    folder.mkdir(parents=True, exist_ok=True)
    np.save(folder / "test.npy", test_picture())
    pictures = {"test": folder / "test.npy"}
    pictures |= {Path(f).stem: Path(f) for f in args.frame}
    failed = False
    for view, look in CASES:
        record = case(view, look, pictures, folder)
        worst = [
            record[name][side][0]
            for name in pictures
            if name in record
            for side in ("blender", "ocio")
        ]
        record["ok"] = bool(worst) and max(worst) <= MOST
        failed |= not record["ok"]
        print(json.dumps(record), flush=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
