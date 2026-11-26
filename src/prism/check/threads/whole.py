"""The whole frame: the threads' preset's picture (and the sun's map, the hosts'
commands sent before the frame) against the stage-wise preset's of the same frame, byte
for byte, at each count of cores and each hand-out policy; where they differ, the first
differing tile, its records and the core that ran it."""

import sys

from prism.check.threads import compare, names
from prism.check.threads.card import closed, read_words, run_frame
from prism.check.threads.sun import cleared, judged, map_of, shadow_host
from prism.core.implementation import hosted
from prism.stages.raster.model.threads import slices
from prism_reference.raster.setup import grid

KEPT = "kept"  # the policy whose slices a core takes is known: slice s to rank s mod n


def say(line):
    """A line of progress, to stderr."""
    print(line, file=sys.stderr, flush=True)


def stagewise_picture(open_loop, name, scene, options=None):
    """The stage-wise preset `name`'s picture of `scene`'s camera (its own loop,
    stopped after): {code, picture, map (None: no sun's pass), sun passes}."""
    loop = open_loop(name, dict(options or {}))
    try:
        frame = loop.frame(scene["camera"], picture=True)
        host = shadow_host(loop)
        drawn = None if host is None else map_of(loop)
        passes = [] if host is None else list(host.passes)
    finally:
        loop.stop()
    say(f"{name}: code {frame.code}, sun passes {passes}")
    return {
        "code": frame.code,
        "picture": frame.picture,
        "map": drawn,
        "passes": passes,
    }


def sun_armed(loop):
    """The sun's map cleared and its command asked for again (as a moved sun asks)
    when a sun is set: the host's passes so far; None without a sun's pass."""
    host = shadow_host(loop)
    if host is None:
        return None
    if host.sun is None:
        return len(host.passes)
    cleared(loop)
    hosted(host, "set")(loop.loaded, "sun", tuple(host.sun_now()))
    return len(host.passes)


def sun_judged(loop, before, want):
    """The sun's passes of this frame and its map against `want`: {} without a map."""
    if before is None or want is None:
        return {}
    passes = shadow_host(loop).passes[before:]
    return {"sun_passes": passes, "map": judged(map_of(loop), want)}


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


def frames(loop, scene, want, policies, cores, phases=0, want_map=None):
    """A frame a policy on `loop` against the picture `want` (and the sun's map
    `want_map` when the loop sends the hosts' commands): {policy: judged}; the first
    bad end stops them."""
    out = {}
    for policy in policies:
        before = sun_armed(loop) if loop.sends else None
        done = run_frame(loop, scene["camera"], phases, policy)
        one = {"code": done["code"], "standing": done["standing"]}
        if done["picture"] is not None:
            one |= compare.pictures(done["picture"], want)
            if not one["equal"]:
                one["first_tile"] |= first_tile(loop, one, policy, cores)
            one |= sun_judged(loop, before, want_map)
            if "map" in one:
                one["equal"] = one["equal"] and one["map"]["equal"]
        out[policy] = one
        say(f"cores {cores}, {policy}: {short(one)}")
        if done["standing"] is not None:
            break
    return out


def short(judged):
    """One line of a judged frame."""
    if judged.get("standing") is not None:
        return f"ended badly ({judged['standing']['code']})"
    drawn = judged.get("map")
    sun = "" if drawn is None else f"; map {short_map(drawn)}"
    if judged.get("equal"):
        return "equal" + sun
    if judged.get("pixels_differ") == 0:
        return "picture equal" + sun
    return (
        f"{judged.get('pixels_differ')} pixels, {judged.get('tiles_differ')} tiles "
        f"differ, first {judged.get('first_tile', {}).get('tile')}{sun}"
    )


def short_map(drawn):
    """One line of a judged map."""
    if drawn["equal"]:
        return f"equal ({drawn['nonzero_pages']} pages drawn)"
    return f"{drawn['bytes_differ']} bytes, {drawn['pages_differ']} pages differ"


def check(
    open_loop,
    threads_name,
    stage_name,
    scene,
    cores_list,
    policies,
    options=None,
    sun=None,
):
    """The whole frame of `scene` by `threads_name` against `stage_name` at each count
    of cores (None: every core) and each policy, both given the sun options `sun`, the
    threads' loop sending the hosts' commands: the record."""
    sun = dict(sun or {})
    want = stagewise_picture(open_loop, stage_name, scene, sun)
    out = {"stagewise": {"preset": stage_name, "code": want["code"]}, "runs": {}}
    out["stagewise"]["sun_passes"] = want["passes"]
    if want["map"] is not None:
        out["stagewise"]["nonzero_pages"] = int(want["map"].any(axis=1).sum())
    if want["picture"] is None:
        return out | {"equal": False}
    for cores in cores_list:
        loop = open_loop(threads_name, {**(options or {}), **sun, "cores": cores})
        loop.sends = True
        try:
            count = cores or loop_cores(loop)
            ran = frames(loop, scene, want["picture"], policies, count, 0, want["map"])
        finally:
            stop = closed(loop)
        out["runs"][str(cores or "all")] = {"frames": ran, "stop": stop}
    judged = [one for ran in out["runs"].values() for one in ran["frames"].values()]
    out["equal"] = bool(judged) and all(one.get("equal") for one in judged)
    return out


def loop_cores(loop):
    """The cores of the loop's group: its option, else every rank of the session."""
    return int(loop.options.get("cores") or loop.session.ranks)
