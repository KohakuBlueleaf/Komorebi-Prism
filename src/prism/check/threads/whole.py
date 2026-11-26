"""The whole frame: the threads' preset's picture against the stage-wise preset's of the
same frame, byte for byte, at each count of cores and each hand-out policy; where they
differ, the first differing tile, its records and the core that ran it."""

import sys

from prism.check.threads import compare, names
from prism.check.threads.card import closed, read_words, run_frame
from prism.stages.raster.model.threads import slices
from prism_reference.raster.setup import grid

KEPT = "kept"  # the policy whose slices a core takes is known: slice s to rank s mod n


def say(line):
    """A line of progress, to stderr."""
    print(line, file=sys.stderr, flush=True)


def stagewise_picture(open_loop, name, scene, options=None):
    """The stage-wise preset `name`'s picture of `scene`'s camera (its own loop,
    stopped after): {code, picture}."""
    loop = open_loop(name, dict(options or {}))
    try:
        frame = loop.frame(scene["camera"], picture=True)
    finally:
        loop.stop()
    say(f"{name}: code {frame.code}")
    return {"code": frame.code, "picture": frame.picture}


def ran_by(policy, slice_of, cores, first=0):
    """The rank that ran slice `slice_of`'s threads: known under `kept` only."""
    if policy != KEPT:
        return None
    return first + slice_of % cores


def first_tile(loop, judged, policy, cores):
    """The first differing tile of `judged` (compare.pictures): its slice, its records
    read back from the records tensor (while the run is loaded), the rank that ran it.
    """
    loaded = loop.loaded
    _, host = names.threads_host(loaded)
    held = names.capacity(host)
    tile = judged["first_tile"]["tile"]
    across, down = grid({"size": loop.size})
    slice_of = int(slices((across, down), held.slice_tiles)["of"][tile])
    words = read_words(loaded.session, names.tensors(host)["records"])
    found = compare.records_of_tile(
        words, tile, judged["first_tile"]["rows"], slice_of, held.slice_records
    )
    return {
        "slice": slice_of,
        "records": [{"number": n, **fields} for n, fields in found],
        "rank": ran_by(policy, slice_of, cores),
    }


def frames(loop, scene, want, policies, cores, phases=0):
    """A frame a policy on `loop` against the picture `want`: {policy: judged}; the
    first bad end stops them."""
    out = {}
    for policy in policies:
        done = run_frame(loop, scene["camera"], phases, policy)
        judged = {"code": done["code"], "standing": done["standing"]}
        if done["picture"] is not None:
            judged |= compare.pictures(done["picture"], want)
            if not judged["equal"]:
                judged["first_tile"] |= first_tile(loop, judged, policy, cores)
        out[policy] = judged
        say(f"cores {cores}, {policy}: {short(judged)}")
        if done["standing"] is not None:
            break
    return out


def short(judged):
    """One line of a judged frame."""
    if judged.get("standing") is not None:
        return f"ended badly ({judged['standing']['code']})"
    if judged.get("equal"):
        return "equal"
    return (
        f"{judged.get('pixels_differ')} pixels, {judged.get('tiles_differ')} tiles "
        f"differ, first {judged.get('first_tile', {}).get('tile')}"
    )


def check(
    open_loop, threads_name, stage_name, scene, cores_list, policies, options=None
):
    """The whole frame of `scene` by `threads_name` against `stage_name` at each count
    of cores (None: every core) and each policy: the record."""
    want = stagewise_picture(open_loop, stage_name, scene)
    out = {"stagewise": {"preset": stage_name, "code": want["code"]}, "runs": {}}
    if want["picture"] is None:
        return out | {"equal": False}
    for cores in cores_list:
        loop = open_loop(threads_name, {**(options or {}), "cores": cores})
        try:
            ran = frames(
                loop, scene, want["picture"], policies, cores or loop_cores(loop)
            )
        finally:
            stop = closed(loop)
        out["runs"][str(cores or "all")] = {"frames": ran, "stop": stop}
    judged = [one for ran in out["runs"].values() for one in ran["frames"].values()]
    out["equal"] = bool(judged) and all(one.get("equal") for one in judged)
    return out


def loop_cores(loop):
    """The cores of the loop's group: its option, else every rank of the session."""
    return int(loop.options.get("cores") or loop.session.ranks)
