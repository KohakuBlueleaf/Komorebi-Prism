"""The field update's check: `updates` update commands (whole, or stepped with the
host's float apply between the steps), then, after the stop, the field's texels, sky and
L0 against the reference's (`expected`), each command's code and its times."""

import numpy as np

from prism.stages.indirect.field_update.host import SCALE_COMMAND
from prism.stages.indirect.field_update.model.numbers import F32
from prism.stages.indirect.field_update.model.regions import element_arrays
from prism.stages.indirect.field_update.model.results import (
    expected,
    field_texels,
    times,
    work_arrays,
)
from prism_reference.indirect.field.pack import PACK_BITS, PACK_SHIFTS

CODE_MOST_ALONE = 1  # the largest code difference without the card's apply
CODE_MOST_PASSES = 12  # with it (the card's tile formats): the largest recorded is 10
NAME = "indirect.field_update"
TRANSPORT = "indirect.transport"


def codes(texels):
    """Each channel's code (rows, 3) of the texels."""
    texels = np.asarray(texels, np.uint32)
    return np.stack(
        [
            (texels >> np.uint32(shift)) & np.uint32((1 << bits) - 1)
            for bits, shift in zip(PACK_BITS, PACK_SHIFTS, strict=True)
        ],
        -1,
    ).astype(np.int64)


def field_numbers(got, want):
    """Two fields' texels compared: the share equal, the largest code
    difference of a channel, whether the has-data bits agree."""
    got, want = np.asarray(got, np.uint32), np.asarray(want, np.uint32)
    return {
        "texels": len(want),
        "share_equal": float(np.mean(got == want)),
        "code_most": int(np.abs(codes(got) - codes(want)).max(initial=0)),
        "has_equal": bool(np.array_equal(got >> 31, want >> 31)),
    }


def relative_most(got, want):
    """The largest |got - want| / |want| over the entries where want is not 0, and the
    count of entries that differ."""
    got, want = np.asarray(got, np.float64), np.asarray(want, np.float64)
    some = want != 0
    rel = np.abs(got[some] - want[some]) / np.abs(want[some])
    return {
        "most": float(rel.max(initial=0.0)),
        "differ": int(np.sum(got != want)),
    }


def verdict(out):
    """Passing: every code 0 and the largest code difference of the field at most
    CODE_MOST_ALONE at 0 bounces or stepped, CODE_MOST_PASSES whole with passes (the
    card's apply in them). {ok, rule, failed}."""
    failed = [f"code {c}" for c in out["codes"] + out["row_codes"] if c != 0]
    if "field" not in out:
        return {"ok": False, "rule": "codes", "failed": failed + ["no field"]}
    code = out["field"]["code_most"]
    alone = out["bounces"] == 0 or out["stepped"]
    most = CODE_MOST_ALONE if alone else CODE_MOST_PASSES
    failed += [f"code most {code}"] if code > most else []
    return {"ok": not failed, "rule": f"code most <= {most}", "failed": failed}


def update_times(rows):
    """The parts in ms the table reports, from a times row: the largest apply of a
    pass told apart; `summed` the passes the last entry of passes_ms holds, if more
    than one."""
    applies = [p["apply"] for p in rows["passes_ms"]]
    if "summed" in rows:
        applies = applies[:-1]
    return {
        "total": rows["total"],
        "fetch": rows["fetch"],
        "zero": rows["zero"],
        "sources": rows["sources"],
        "rows": rows["rows"],
        "pack": rows["pack"],
        "store": rows["store"],
        "apply_most": max(applies, default=None),
        "unit": rows["unit"],
        "passes_ms": rows["passes_ms"],
    } | ({"summed": rows["summed"]} if "summed" in rows else {})


def check(loaded):
    """The run's `updates` updates (`stepped`: the host's apply between the steps),
    each one's scale word asked for (field_scale); after the stop, the last field
    against the reference's, each command's code, the times rows, the scale words
    against the rows'."""
    host = loaded.hosts[NAME]
    options = loaded.options
    stepped = bool(options.get("stepped"))
    xs = {}
    commands, hosts, pages, scales = [], [], None, []
    for _ in range(int(options.get("updates", 2))):
        code, seconds = host.run(stepped, on_x=lambda p, x: xs.__setitem__(p, x))
        commands.append(code)
        hosts.append(seconds)
        if code != 0:
            break
        pages = host.field_pages()
        scales.append(loaded.serve(SCALE_COMMAND))
    loaded.stop()
    rows = times(loaded.region("field_times"))
    work = work_arrays(loaded.region("field_work"), host.model)
    transport = loaded.hosts[TRANSPORT].results(loaded)
    want = expected(host.lights, host.model, host.bounces)
    out = {
        "scene": host.scene,
        "sun": host.sun,
        "bounces": host.bounces,
        "stepped": stepped,
        "codes": commands,
        "row_codes": [row["code"] for row in rows],
        "host_s": hosts,
        "times": [update_times(row) for row in rows],
        "transport": transport,
    }
    if pages is None:
        out["verdict"] = verdict(out)
        return out
    got = field_texels(pages, host.model)
    scale = rows[-1]["scale"]
    out["field"] = field_numbers(got, want["texels"])
    out["pages_equal"] = bool(np.array_equal(pages, want["pages"]))
    out["scale"] = {
        "card": scale,
        "reference": float(want["scale"]),
        "relative": abs(scale - float(want["scale"])) / float(want["scale"]),
    }
    out["sky"] = relative_most(work["sky"], want["sky"])
    out["l0"] = relative_most(work["l0"], want["l0"])
    want_e = want["sky"] + sum(want["passes"], np.zeros_like(want["sky"]))
    out["e"] = relative_most(work["total"], want_e.astype(F32))
    if stepped and want["passes"]:
        albedo = element_arrays(host.model, host.lights)["albedo"]
        sources = [want["l0"]] + [albedo * e for e in want["passes"][:-1]]
        out["x"] = {p: relative_most(x, sources[p]) for p, x in xs.items()}
    units = [F32(1) / F32((1 << bits) - 1) for bits in PACK_BITS]
    out["scale_words_equal"] = [
        scale == int(F32(row["scale"]).view(np.uint32))
        for scale, row in zip(scales, rows, strict=False)
    ]
    out["unit"] = relative_most(
        rows[-1]["unit"], [(u * u) * F32(want["scale"]) for u in units]
    )
    out["verdict"] = verdict(out)
    return out
