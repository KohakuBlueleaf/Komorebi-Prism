"""The geometry half: the count pull, the sums and the place pull of a view run, then
the records, the slices' words, each core's counts, row histograms, positions pages (the
words the sums write) and each layer's lists read back against the model for the same
log (the lists as the same entries an item, their order reported)."""

import numpy as np

from prism.check.threads import compare, names
from prism.check.threads.card import closed, read_per_core, read_words, run_frame
from prism.check.threads.model import (
    counts_image,
    log_cores,
    positions_image,
    positions_used,
    records_image,
    rows_image,
    slices_image,
)
from prism.check.threads.tile_half import model_of
from prism.stages.raster.model.numbers import SLOT
from prism.stages.raster.model.threads import R
from prism_reference.raster import cull
from prism_reference.raster.setup import grid


def read_back(loop, laid_one, cores):
    """What the view left, read after the stop: the log, the slices' words, the
    records and each layer's per-core pages and list slots."""
    loaded = loop.loaded
    _, host = names.threads_host(loaded)
    held = names.capacity(host)
    tensors = names.tensors(host)
    session = loaded.session
    ranges = int(laid_one["ranges"]["count"].sum())
    out = {
        "log": loaded.region(names.LOG),
        "slices": np.frombuffer(loaded.region(names.SLICES), np.uint32),
        "records": read_words(session, tensors["records"]).reshape(-1, R["TR_WORDS"]),
        "ranges": ranges,
        "layers": [],
    }
    for layer, lists in enumerate(laid_one["lists"]):
        one = {}
        for name in ("counts", "rows", "positions"):
            tensor = tensors[name][layer]
            one[name] = read_per_core(session, tensor, cores, tensor.page_bytes // 4)
        flat = read_words(session, tensors["lists"][layer]).reshape(-1)
        count = len(lists["slots"])
        one["lists"] = flat[: count * SLOT].reshape(-1, SLOT)
        out["layers"].append(one)
    out["slices"] = out["slices"][: held.slices * R["TS_WORDS"]].reshape(
        held.slices, -1
    )
    return out


def judged(laid, got, held):
    """Each comparison of what the card left against the model `laid`: [result]."""
    records = got["records"][: held.slices * held.slice_records]
    out = [
        compare.records(records, records_image(laid, held), held.slice_records),
        compare.exact("slices", got["slices"], slices_image(laid, held)),
    ]
    for layer, one in enumerate(got["layers"]):
        words = {name: one[name].shape[1] for name in ("counts", "rows", "positions")}
        for name, image in (
            ("counts", counts_image(laid, layer, words["counts"])),
            ("rows", rows_image(laid, layer, words["rows"])),
        ):
            out.append(compare.exact(f"{name}.{layer}", one[name], image))
        used = positions_used(laid, words["positions"])
        image = positions_image(laid, layer, words["positions"])
        judged_used = compare.exact(
            f"positions.{layer}", one["positions"][:, used], image[:, used]
        )
        out.append(judged_used | {"words_used": int(used.sum())})
        out.append(compare.lists(laid, layer, one["lists"]))
    return out


def never_dealt(host, scene):
    """(ranges,) bool: the view's ranges in a group the cull finds outside its view
    (prism_reference.raster.cull outside), layer after layer; none without the cull."""
    out = []
    for name in host.layers:
        ranges = host.ranges_of(host.scenes[name])
        if not host.cull:
            out.append(np.zeros(len(ranges), dtype=bool))
            continue
        groups = cull.group_boxes(ranges, host.group_ranges)
        hidden = cull.outside(scene["camera"], groups, grid(scene))
        out.append(np.repeat(hidden, host.group_ranges)[: len(ranges)])
    return np.concatenate(out)


def run_once(open_loop, threads_name, scene, cores, options=None):
    """One view's count, sums and place at `cores` (None: every core), read back after
    the stop and judged against the model for the card's log: its record."""
    loop = open_loop(threads_name, {**(options or {}), "cores": cores})
    phases = names.mask("count", "sums", "place")
    out = {}
    try:
        laid_one = model_of(loop, scene)
        done = run_frame(loop, scene["camera"], phases, picture=False)
        out = {"code": done["code"], "standing": done["standing"]}
        count = cores or int(loop.options.get("cores") or loop.session.ranks)
        stop = closed(loop)
        if done["standing"] is not None:
            return out | {"stop": stop}
        got = read_back(loop, laid_one, count)
    finally:
        closed(loop)
    _, host = names.threads_host(loop.loaded)
    held = names.capacity(host)
    try:
        untaken = never_dealt(host, scene)
        log, ranks = log_cores(got["log"], got["ranges"], untaken)
        laid = model_of(loop, scene, log, count)
    except ValueError as error:
        return out | {"stop": stop, "model": str(error), "equal": False}
    results = judged(laid, got, held)
    return out | {
        "stop": stop,
        "ranks_counted": len(ranks),
        "never_dealt": int(untaken.sum()),
        "results": results,
        "equal": all(one["equal"] for one in results),
    }


def check(open_loop, threads_name, scene, cores_list, options=None):
    """The geometry half of `scene` by `threads_name` at each count of cores: the
    record."""
    runs = {
        str(cores or "all"): run_once(open_loop, threads_name, scene, cores, options)
        for cores in cores_list
    }
    return {"runs": runs, "equal": all(one.get("equal") for one in runs.values())}
