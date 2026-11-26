"""The account of the threads' form, one way of handing out a run: `stagewise` (the
stage-wise preset; its first picture written to --want) or a policy of the threads'
preset (each picture judged against --want); the frame's and each phase's time from the
times rows. The record to --out; one JSON line of its summary. Example: python
scripts/run/threads_account.py --pipeline textured --scene sponza --view overview
--size 1920 1080 --way order --want W.npy --out R.json --card 0
"""

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

import komorebi as km
import numpy as np
from prism_cli.preset import opened

from prism.check.threads import account, names
from prism_reference.scene.camera import with_size

ROOT = Path(__file__).resolve().parents[2]
SUFFIX = "_threads"


def parse():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--pipeline", default="textured", help="a stage-wise preset")
    parser.add_argument("--scene", required=True)
    parser.add_argument("--view", default=None)
    parser.add_argument("--size", type=int, nargs=2, default=None, help="W H")
    parser.add_argument("--frames", type=int, default=16)
    parser.add_argument(
        "--way", required=True, choices=[account.STAGEWISE, *names.POLICIES]
    )
    parser.add_argument("--want", type=Path, required=True, help="the picture (.npy)")
    parser.add_argument("--card", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True, help="the record's file")
    parser.add_argument(
        "--account", type=int, default=0, help="records a core's page (0: none)"
    )
    parser.add_argument(
        "--trace", type=int, default=0, help="Komorebi's trace: commands a core"
    )
    parser.add_argument(
        "--heavy", type=int, default=None, help="the threads' option heavy (a weight)"
    )
    return parser.parse_args()


def commit():
    """The tree's commit and whether it holds changes."""
    head = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return {"head": head, "changed": bool(dirty)}


def run(args, session, preset, camera, mhz):
    """The way's frames on `session`: its part of the record."""
    if args.way == account.STAGEWISE:
        want, out = account.stagewise(preset.open(session), camera, args.frames)
        if want is not None:
            np.save(args.want, want)
        return out
    want = np.load(args.want)
    loop = preset.open(session)  # the real loop (prism.loop.Loop), its threads' form
    return account.threads(loop, camera, args.frames, args.way, want, mhz)


def main():
    args = parse()
    name = args.pipeline + ("" if args.way == account.STAGEWISE else SUFFIX)
    try:
        given = {"account": args.account} if args.account else {}
        given |= {"trace": args.trace} if args.trace else {}
        given |= {} if args.heavy is None else {"heavy": args.heavy}
        preset = opened(name, args.scene, args.view, args.size, given)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    camera = with_size(preset.scene, preset.size)["camera"]
    case = {
        "preset": name,
        "way": args.way,
        "scene": args.scene,
        "view": args.view,
        "size": list(preset.size),
        "frames": args.frames,
        "card": args.card,
        "account": args.account,
        "trace": args.trace,
        "heavy": args.heavy,
        "date": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "komorebi": km.__version__,
        "tree": commit(),
    }
    with km.Session(card=args.card) as session:
        case["aiclk_mhz"] = [account.clock(args.card)]
        out = run(args, session, preset, camera, case["aiclk_mhz"][0])
        case["aiclk_mhz"].append(account.clock(args.card))
    times = account.medians(out["rows"])
    held = out.pop("records", None)
    trace = out.pop("trace", None)
    record = {"case": case, **out, "times": times, "phases": account.phases(times)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if held:
        frames = {f"frame_{i}": rows for i, (rows, _) in enumerate(held)}
        frames |= {f"blocks_{i}": blocks for i, (_, blocks) in enumerate(held)}
        frames |= {} if trace is None else {"trace": np.asarray(trace)}
        np.savez_compressed(args.out.with_suffix(".records.npz"), **frames)
    args.out.write_text(json.dumps(record, indent=1) + "\n")
    judged = out.get("judged") or [{"equal": s} for s in out.get("same_as_first", [])]
    summary = {
        "way": args.way,
        "codes": sorted(set(out["codes"])),
        "equal": bool(judged) and all(one["equal"] for one in judged),
        "frame_ms": times.get("frame"),
    }
    print(json.dumps(summary), flush=True)
    return 0 if summary["equal"] and summary["codes"] == [0] else 1


if __name__ == "__main__":
    sys.exit(main())
