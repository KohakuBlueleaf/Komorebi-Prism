"""Frames while the field's update runs: each frame's picture against the stage-wise
pictures of the field before and after its update (its own beside form), which one it
equals; the ranks the frame's pulls took while an update waited."""

import numpy as np

from prism.check.threads import compare, whole
from prism.check.threads.card import closed, run_frame
from prism.check.threads.model import PORTS_CORES
from prism.check.threads.names import STATE
from prism.check.threads.update import field_host
from prism.core.resources import TIMES_ROWS
from prism.program.threads.hosts import transport_of

BESIDE = "update_beside"  # the stage-wise option: the update beside the frames
TOOK = "light_field"  # the light unit's result: 1 + the field's half a frame took
VERSIONS = {1: "before", 2: "after"}  # what it names when the update writes half 1
AFTER_MOST = 2  # frames sent after the update was seen served


def stagewise_beside(open_loop, name, scene, options):
    """The stage-wise preset `name` with its update beside the frames: the picture of
    its first frame (the field before) and of the frame after the update (after)."""
    loop = open_loop(name, {**options, BESIDE: True})
    try:
        before = loop.frame(scene["camera"], picture=True)
        code = loop.collect(wait=True)
        after = loop.frame(scene["camera"], picture=True)
    finally:
        loop.stop()
    whole.say(f"{name} beside: codes {before.code}, update {code}, {after.code}")
    return {
        "codes": [before.code, code, after.code],
        "before": before.picture,
        "after": after.picture,
    }


def version_of(picture, want):
    """Which of `want`'s pictures `picture` equals ('before', 'after', both or none),
    and the pixels it differs from each."""
    judged = {key: compare.pictures(picture, want[key]) for key in ("before", "after")}
    equal = [key for key, one in judged.items() if one["equal"]]
    return {
        "equals": equal,
        "pixels_differ": {key: one["pixels_differ"] for key, one in judged.items()},
    }


def frames_during(loop, scene, policy, want, most):
    """Frames sent one after another from the update's start (the first attempt sends
    the SUN and starts the graph) until AFTER_MOST after its end was seen, at most
    `most`: each its code, whether the update was still unserved when it was sent
    (`sent_running`), its version."""
    graph = field_host(loop).graph
    out, after = [], 0
    for number in range(most):
        done = run_frame(loop, scene["camera"], 0, policy)
        one = {"code": done["code"], "sent_running": graph.handle is not None}
        one["row"] = loop.loaded.served - 1
        if done["picture"] is not None:
            one |= version_of(done["picture"], want)
        if done["standing"] is not None:
            one["standing"] = done["standing"]
        out.append(one)
        whole.say(f"frame {number}: {one.get('equals')}, sent {one['sent_running']}")
        if done["standing"] is not None:
            break
        after += not one["sent_running"]
        if after >= AFTER_MOST:
            break
    return out


def reported(loop, frames):
    """Each frame's field as the light unit's result in its times row (read after the
    stop): `took` (1 + the half; 0 the table's) and whether it names its picture's."""
    loaded = loop.loaded
    if TOOK not in loaded.layout.results:
        return
    words = loaded.layout.times_words
    raw = np.frombuffer(loaded.thread.read("times"), dtype=np.uint32)
    rows = raw[: TIMES_ROWS * words].reshape(TIMES_ROWS, words)
    (word,) = loaded.layout.row_words(loaded.layout.results[TOOK])
    for one in frames:
        took = int(rows[one["row"] % TIMES_ROWS][word])
        one["took"] = took
        named = "before" if took == 0 else VERSIONS.get(took)
        one["took_agrees"] = one.get("equals") == [named]


def placement(loop):
    """The last view's tile pull as the choice kept it (read after the stop): its
    group's first rank and count, the ranks that told."""
    raw = np.frombuffer(loop.loaded.region(STATE), dtype=np.uint32)
    head, cores = raw[:8], raw[8 : 8 + 4 * PORTS_CORES].reshape(-1, 4)
    told = [c for c in range(PORTS_CORES) if cores[c, 3]]
    return {
        "first": int(head[3]),
        "count": int(head[4]),
        "told": [min(told), max(told), len(told)] if told else [],
    }


def judged(frames):
    """Every frame ended and equals exactly one version (the one it reports, when it
    reports one); the versions in order never go back from after to before."""
    versions = [one.get("equals") for one in frames]
    whole_ = all(one["code"] == 0 and len(one.get("equals", [])) == 1 for one in frames)
    order = [v[0] for v in versions if v and len(v) == 1]
    agree = all(one.get("took_agrees", True) for one in frames)
    return whole_ and agree and order == sorted(order, key=["before", "after"].index)


def check(open_loop, threads_name, stage_name, scene, policy, options, sun, most, deal):
    """Frames of `threads_name` while its update of `sun` runs against `stage_name`'s
    pictures before and after (its beside form, its weights dealt to `deal` cores);
    then one frame sent right after an update's start, the run stopped, its pulls'
    ranks: the record."""
    want = stagewise_beside(open_loop, stage_name, scene, {**sun, "cores": deal})
    out = {"stagewise": {"codes": want["codes"], "deal": deal}}
    out["stagewise"]["before_after"] = compare.pictures(want["before"], want["after"])[
        "pixels_differ"
    ]
    loop = open_loop(threads_name, {**options, **sun})
    try:
        out["update_cores"] = transport_of(loop.loaded.assembled)[1].cores
        out["frames"] = frames_during(loop, scene, policy, want, most)
    finally:
        out["stop"] = closed(loop)
    reported(loop, out["frames"])
    whole.say(f"reported: {[one.get('took') for one in out['frames']]}")
    loop = open_loop(threads_name, {**options, **sun})
    cores = transport_of(loop.loaded.assembled)[1].cores, field_host(loop).graph.cores
    try:
        first = frames_during(loop, scene, policy, want, 1)
    finally:
        stop = closed(loop)
    reported(loop, first)
    out["first_frame"] = {"frame": first, "stop": stop, "pulls": placement(loop)}
    out["first_frame"]["cores"] = {"update": cores[0], "graph": cores[1]}
    whole.say(f"first frame's pulls: {out['first_frame']['pulls']}")
    out["equal"] = judged(out["frames"]) and judged(first)
    return out
