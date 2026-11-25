"""The preset `field` on one card: assembled, loaded, its check run (whole or stepped);
one JSON line, and the record written to <out>/<scene>_b<bounces>[_stepped].json.
Example: python scripts/run/field.py --scene sponza --bounces 2 --stepped"""

import argparse
import json
import runpy
from pathlib import Path

import komorebi as km

from prism.check import harness
from prism.program.assemble import assemble
from prism.program.loaded import load

ROOT = Path(__file__).resolve().parents[2]
PRESET = ROOT / "configs" / "pipeline" / "field.py"
CHECKED = "indirect.field_update"


def parse():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--scene", required=True)
    parser.add_argument(
        "--bounces", type=int, default=None, help="the preset's if none"
    )
    parser.add_argument("--stepped", action="store_true")
    parser.add_argument("--updates", type=int, default=None)
    parser.add_argument("--card", type=int, default=0)
    parser.add_argument(
        "--out", type=Path, default=ROOT / "measurements" / "field_update" / "runs"
    )
    return parser.parse_args()


def main():
    args = parse()
    preset = runpy.run_path(str(PRESET))
    pipeline, options = preset["PIPELINE"], dict(preset["OPTIONS"])
    options["stepped"] = args.stepped
    for name in ("bounces", "updates"):
        if getattr(args, name) is not None:
            options[name] = getattr(args, name)
    tag = f"{args.scene}_b{options['bounces']}" + ("_stepped" if args.stepped else "")
    with km.Session(card=args.card) as session:
        assembled = assemble(pipeline, session, args.scene, options)
        loaded = load(assembled, session)
        try:
            check = next(i.check for i in pipeline.implementations if i.name == CHECKED)
            record = harness.run(check, loaded, args.out / f"{tag}.json")
        finally:
            result = loaded.stop()
    if result["error_name"] != "none":
        raise km.KomorebiError(f"field: the run ended with {result['error_name']}")
    print(json.dumps(record, default=float), flush=True)


if __name__ == "__main__":
    main()
