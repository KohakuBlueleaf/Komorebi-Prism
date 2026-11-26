"""The account of a preset's frames on one card: each command's cores, spread, bytes,
counts and closure (prism.check.account), written to
measurements/account/<scene>_<view>_<W>_<H>_<pipeline>.json; one JSON line of its
summary. Example: python scripts/run/account.py --pipeline gi --scene S --view
overview --size 1024 1024 --frames 16 --card 1
"""

import argparse
import contextlib
import io
import json
import re
import sys
from pathlib import Path

import komorebi as km
from prism_cli.preset import opened

from prism.check.account import account

ROOT = Path(__file__).resolve().parents[2]
TRACE = 1024  # commands traced a core: the load's and 16 frames' with room
NUMBERS = re.compile(r"\[\s*([-0-9.eE+,\s]*?)\s*\]")
TABLE = "L1 budget of a core"
TABLE_ROW = re.compile(r"^  (\S.*?)\s+([\d,]+) B(?: of ([\d,]+) B)?$")


class Kept(io.TextIOBase):
    """Standard output passed on and kept."""

    def __init__(self):
        self.kept = []

    def write(self, text):
        self.kept.append(text)
        return sys.__stdout__.write(text)


def printed_table(text):
    """The last L1 budget table the load printed, as [what, bytes] rows, the total and
    the bytes left for them."""
    lines = text.split(TABLE)[-1].splitlines()[1:] if TABLE in text else []
    rows, free = [], None
    for line in lines:
        match = TABLE_ROW.match(line)
        if not match:
            break
        rows.append([match.group(1), int(match.group(2).replace(",", ""))])
        free = int(match.group(3).replace(",", "")) if match.group(3) else free
    return {"rows": rows, "free": free}


def parse():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--pipeline", default="gi", help="a preset's name")
    parser.add_argument("--scene", required=True, help="a public scene")
    parser.add_argument("--view", default="overview", help="a public scene's view")
    parser.add_argument("--size", type=int, nargs=2, default=None, help="W H")
    parser.add_argument("--frames", type=int, default=16)
    parser.add_argument("--card", type=int, default=0)
    parser.add_argument("--trace", type=int, default=TRACE, help="0: no trace")
    parser.add_argument("--out", type=Path, default=None, help="the record's file")
    return parser.parse_args()


def dumped(record):
    """The record as indented JSON, each list of numbers on one line."""
    text = json.dumps(record, indent=1, default=float)
    return NUMBERS.sub(lambda m: "[" + re.sub(r"\s+", "", m.group(1)) + "]", text)


def main():
    args = parse()
    options = {"frames": args.frames, "trace": args.trace}
    try:
        preset = opened(args.pipeline, args.scene, args.view, args.size, options)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    size = preset.size
    name = "_".join([args.scene, args.view, *map(str, size), args.pipeline])
    kept = Kept()
    with km.Session(card=args.card) as session:
        with contextlib.redirect_stdout(kept):
            loop = preset.open(session)
        try:
            record = account(loop, args.frames)
        finally:
            loop.stop()
    record["case"] |= {"scene": args.scene, "view": args.view}
    record["l1"]["printed"] = printed_table("".join(kept.kept))
    out = args.out or ROOT / "measurements" / "account" / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dumped(record) + "\n")
    summary = {
        "case": record["case"],
        "codes": sorted(set(record["codes"])),
        "frames_traced": record["frames_traced"],
        "frame_ms": record["frame_ms"].get("frame"),
        "thread_ms": record["thread_ms"],
        "closure": record["closure"],
    }
    print(json.dumps(summary, default=float), flush=True)


if __name__ == "__main__":
    main()
