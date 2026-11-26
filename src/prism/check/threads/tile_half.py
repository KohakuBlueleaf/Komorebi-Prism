"""The tile half: the model's records, slices' words and lists of a view written into
the card's tensors, only the tile pull's phase of the view run, and the picture read
back against the stage-wise preset's of the same frame, byte for byte; at each count
of cores and each hand-out policy."""

from prism.check.threads import names, whole
from prism.check.threads.card import closed, write_words
from prism.check.threads.layers import frame_layers
from prism.check.threads.model import laid_out, records_image, slices_image, view_of

LAYERS = "frame_layers"  # the option naming the frame's layers in order


def layers_of(loop, scene):
    """The frame's layers as the card holds them for the loop's options."""
    options = loop.options
    return frame_layers(
        scene, options.get("materials"), options.get("lights"), options.get(LAYERS)
    )


def model_of(loop, scene, log=None, cores=None):
    """The model's layout of `scene` for the loop's threads' host (its capacity and
    numbers), `log` the core of each range (None: one core)."""
    _, host = names.threads_host(loop.loaded)
    held = names.capacity(host)
    given = names.numbers(host)
    return laid_out(
        layers_of(loop, scene),
        view_of(scene),
        held,
        given["heavy"],
        given["range_blocks"],
        log,
        cores,
        host.held.wide,
    )


def written(loop, laid):
    """The model's records, lists (a layer each) and slices' words written into the
    loop's tensors and the dispatcher's slices region: {what: words written}."""
    loaded = loop.loaded
    _, host = names.threads_host(loaded)
    held = names.capacity(host)
    tensors = names.tensors(host)
    if len(laid["lists"]) > len(tensors["lists"]):
        raise ValueError(
            f"the model has {len(laid['lists'])} layers, the host "
            f"{len(tensors['lists'])} lists tensors"
        )
    records = records_image(laid, held)
    write_words(loaded.session, tensors["records"], records)
    out = {"records": int(records.size)}
    for layer, lists in enumerate(laid["lists"]):
        write_words(loaded.session, tensors["lists"][layer], lists["slots"])
        out[f"lists.{layer}"] = int(lists["slots"].size)
    words = slices_image(laid, held)
    loaded.write(names.SLICES, words)
    out["slices"] = int(words.size)
    return out


def check(
    open_loop, threads_name, stage_name, scene, cores_list, policies, options=None
):
    """The tile half of `scene` by `threads_name` against `stage_name`'s picture at
    each count of cores (None: every core) and each policy, the threads' preset's
    `options` besides: the record."""
    want = whole.stagewise_picture(open_loop, stage_name, scene)
    out = {"stagewise": {"preset": stage_name, "code": want["code"]}, "runs": {}}
    if want["picture"] is None:
        return out | {"equal": False}
    tile = names.mask("tile")
    laid = None
    for cores in cores_list:
        loop = open_loop(threads_name, {**(options or {}), "cores": cores})
        try:
            laid = laid or model_of(loop, scene)
            given = written(loop, laid)
            count = cores or whole.loop_cores(loop)
            ran = whole.frames(loop, scene, want["picture"], policies, count, tile)
        finally:
            stop = closed(loop)
        out["runs"][str(cores or "all")] = {
            "written": given,
            "frames": ran,
            "stop": stop,
        }
    judged = [one for ran in out["runs"].values() for one in ran["frames"].values()]
    out["equal"] = bool(judged) and all(one.get("equal") for one in judged)
    if laid is not None:
        out["model"] = summary(laid)
    return out


def summary(laid):
    """The model's sizes: slices, records, items cut into bands, entries a layer."""
    return {
        "slices": len(laid["slice_words"]),
        "records": int(laid["slice_words"][:, 0].sum()),
        "items": len(laid["items"]),
        "tiles_in_bands": int((laid["item_count"] > 1).sum()),
        "entries": [len(one["slots"]) for one in laid["lists"]],
    }
