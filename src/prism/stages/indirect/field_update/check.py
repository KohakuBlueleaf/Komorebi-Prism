"""The field update's check: `updates` update commands (whole, or stepped with the
host's float apply between the steps), then, after the stop, the field's texels, sky and
L0 against the reference's (`expected`; whole with passes, with the card's apply
emulated, and that against float32's as the format's error), each command's code and its
times."""

import numpy as np

from prism.stages.indirect.field_update.host import SCALE_COMMAND
from prism.stages.indirect.field_update.model.kept import kept
from prism.stages.indirect.field_update.model.numbers import F32
from prism.stages.indirect.field_update.model.regions import element_arrays
from prism.stages.indirect.field_update.model.results import (
    field_texels,
    times,
    work_arrays,
)
from prism.stages.indirect.transport.plan.emulate import emulate
from prism.stages.indirect.transport.plan.weights import decode_weights
from prism_reference.indirect.field.pack import PACK_BITS, PACK_SHIFTS

CODE_MOST = 1  # the largest code difference against the reference judged by
FORMAT_LIT = 0.01  # a value counted in the format's per cent: this share of the scale
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


def card_product(transport):
    """The product as the card's apply computes it: `transport`'s set and its encoded
    weights, emulated."""
    s, w = transport.set, decode_weights(transport.raw)
    return lambda blocks, weights, x: emulate(s, w, x)


def format_error(card, exact):
    """The field with the card's apply emulated (`card`, expected's) against float32's
    (`exact`): p99 and largest code difference of a channel, and p99 and largest of the
    value's relative difference in per cent where float32's is FORMAT_LIT of its scale.
    """
    gap = np.abs(codes(card["texels"]) - codes(exact["texels"])).ravel()
    lit = exact["values"] >= FORMAT_LIT * float(exact["scale"])
    rel = np.abs(card["values"][lit] - exact["values"][lit]) / exact["values"][lit]
    return {
        "code_p99": float(np.percentile(gap, 99)) if gap.size else 0.0,
        "code_most": int(gap.max(initial=0)),
        "percent_p99": float(100 * np.percentile(rel, 99)) if rel.size else 0.0,
        "percent_most": float(100 * rel.max(initial=0.0)),
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
    """Passing: every code 0 and the largest code difference of the field against the
    reference it is judged by at most CODE_MOST. {ok, rule, failed}."""
    failed = [f"code {c}" for c in out["codes"] + out["row_codes"] if c != 0]
    if "field" not in out:
        return {"ok": False, "rule": "codes", "failed": failed + ["no field"]}
    code = out["field"]["code_most"]
    failed += [f"code most {code}"] if code > CODE_MOST else []
    return {"ok": not failed, "rule": f"code most <= {CODE_MOST}", "failed": failed}


def judged_by(lights, model, bounces, transport, stepped):
    """The reference the field is judged by and float32's, kept (`model/kept.py`): with
    passes and whole, the card's apply emulated (`card_product` of `transport`: its
    folder, set and raw), else float32's own."""
    exact = kept(lights, model, bounces)
    if stepped or not exact["passes"]:
        return exact, exact
    card = kept(
        lights, model, bounces, transport.folder, lambda: card_product(transport)
    )
    return card, exact


def update_times(rows):
    """The parts in ms the table reports, from a times row: the largest apply of a
    pass told apart; `summed` the passes the last entry of passes_ms holds, if more
    than one; `span` in the job's form."""
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
    } | {key: rows[key] for key in ("summed", "span") if key in rows}


def check(loaded):
    """The run's `updates` updates (`stepped`: the host's apply between the steps),
    each one's scale word asked for (field_scale); after the stop, the last field
    against the reference's, each command's code, the times rows, the scale words
    against the rows'."""
    loaded = getattr(loaded, "loaded", loaded)  # a loop's run, or the run itself
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
    want, exact = judged_by(
        host.lights, host.model, host.bounces, loaded.hosts[TRANSPORT], stepped
    )
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
    out["judged_by"] = "float32" if want is exact else "the card's apply emulated"
    if want is not exact:
        out["format"] = format_error(want, exact)
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
