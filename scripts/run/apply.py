"""The preset `apply` on one card: assembled, loaded, its check run; one JSON line,
and the record written to <out>/apply_<scene>[_frame].json (--frame-compute: Apply made
with the frame program's compute set).
Example: python scripts/run/apply.py --scene sponza --calls 32"""

import argparse
import json
import runpy
from pathlib import Path

import komorebi as km

from prism.check import harness
from prism.core.compute import FRAME_COMPUTE
from prism.program.assemble import assemble
from prism.program.loaded import load

ROOT = Path(__file__).resolve().parents[2]
PRESET = ROOT / "configs" / "pipeline" / "apply.py"
SCENES = ("sponza", "bistro_interior")


def parse():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--scene", choices=SCENES, required=True)
    parser.add_argument("--calls", type=int, default=None, help="the preset's if none")
    parser.add_argument("--card", type=int, default=0)
    parser.add_argument("--frame-compute", action="store_true")
    parser.add_argument("--out", type=Path, default=ROOT / "measurements" / "apply")
    return parser.parse_args()


def main():
    args = parse()
    preset = runpy.run_path(str(PRESET))
    pipeline, options = preset["PIPELINE"], dict(preset["OPTIONS"])
    if args.calls is not None:
        options["calls"] = args.calls
    if args.frame_compute:
        options["compute"] = FRAME_COMPUTE
    name = f"apply_{args.scene}" + ("_frame" if args.frame_compute else "")
    with km.Session(card=args.card) as session:
        assembled = assemble(pipeline, session, args.scene, options)
        loaded = load(assembled, session)
        try:
            check = pipeline.implementations[0].check
            record = harness.run(check, loaded, args.out / f"{name}.json")
        finally:
            result = loaded.stop()
    if result["error_name"] != "none":
        raise km.KomorebiError(f"apply: the run ended with {result['error_name']}")
    print(json.dumps(record, default=float), flush=True)


if __name__ == "__main__":
    main()
