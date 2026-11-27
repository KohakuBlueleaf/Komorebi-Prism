"""The preset `field` on one card: assembled, loaded, its check run (whole or stepped);
one JSON line, and the record written to <out>/<scene>_b<bounces>[_stepped].json.
`--reference`: no card; the check's references made and kept (run it before the card's
lock is taken). Example: python scripts/run/field.py --scene sponza --bounces 2 --stepped
"""

import argparse
import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import komorebi as km

from prism.check import harness
from prism.program.assemble import assemble
from prism.program.loaded import load
from prism.stages.indirect.field_update.check import judged_by
from prism.stages.indirect.field_update.host import sun_moved
from prism.stages.indirect.transport.host import set_folder
from prism.stages.indirect.transport.plan.set import load as load_set
from prism.stages.indirect.transport.plan.weights import encode_weights
from prism_reference.direct.lights import bounce_count
from prism_reference.indirect.bounces import bounces_of
from prism_reference.indirect.files import load_model

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
    parser.add_argument("--reference", action="store_true")
    parser.add_argument(
        "--out", type=Path, default=ROOT / "measurements" / "field_update" / "runs"
    )
    return parser.parse_args()


def reference(scene, options):
    """The check's references for the host's lights at the options' sun and bounces,
    made and kept (`judged_by`), without a card."""
    lights = sun_moved(scene, options.get("sun"))
    model = load_model(lights["indirect"])
    given = options.get("bounces")
    bounces = bounces_of(lights, model) if given is None else bounce_count(given)
    folder = set_folder(scene)
    s = load_set(folder)
    transport = SimpleNamespace(folder=folder, set=s, raw=encode_weights(s))
    judged_by(lights, model, bounces, transport, options["stepped"])


def main():
    args = parse()
    preset = runpy.run_path(str(PRESET))
    pipeline, options = preset["PIPELINE"], dict(preset["OPTIONS"])
    options["stepped"] = args.stepped
    for name in ("bounces", "updates"):
        if getattr(args, name) is not None:
            options[name] = getattr(args, name)
    tag = f"{args.scene}_b{options['bounces']}" + ("_stepped" if args.stepped else "")
    if args.reference:
        reference(args.scene, options)
        return
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
