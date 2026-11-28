"""The DEPTH view alone: a set sun, the model's records, slices and lists of the sun's
view written, the SUN command run with the tile pull's phase only, the shadow map's
pages read back against the stage-wise preset's map of the same sun, byte for byte; at
each count of cores and each hand-out policy. The map is one quadrant (one view)."""

import komorebi as km
import numpy as np

from prism.check.threads import names, tile_half, whole
from prism.check.threads.card import closed, set_frame
from prism.check.threads.model import PORTS_CORES, laid_out
from prism.check.threads.standing import standing
from prism.check.threads.sun import cleared, judged, map_of, shadow_host
from prism.core.implementation import hosted
from prism.program.dispatch.thread import CHOOSE
from prism.stages.direct.shadow_pcf.model.region import (
    QUADRANT,
    across_of,
    quadrant_cameras,
)
from prism_reference.scene.frame import frame_grid

SUN = "sun"  # its command


def lights_of(lights, side):
    """The scene's prepared `lights` with a shadow map of `side` (None: as they are);
    a map smaller than its side is the card's to draw."""
    if lights is None or side is None:
        return lights
    return {**lights, "shadow_side": np.int32(side)}


def stagewise_map(open_loop, name, scene, options):
    """The stage-wise preset `name`'s map after its first frame (its SUN sent, the sun
    set): {code, map}."""
    loop = open_loop(name, dict(options))
    try:
        frame = loop.frame(scene["camera"])
        loop.collect(wait=True)
        host = shadow_host(loop)
        out = {"code": frame.code, "passes": list(host.passes), "map": map_of(loop)}
    finally:
        loop.stop()
    whole.say(f"{name}: code {out['code']}, sun passes {out['passes']}")
    return out


def depth_view(loop):
    """The model's view of the sun's one quadrant: its camera, size, map pages."""
    host = shadow_host(loop)
    if across_of(host.lights) != 1:
        raise ValueError("the depth half runs a map of one quadrant (shadow_side)")
    camera = quadrant_cameras(host.moved())[0]
    return {
        "camera": np.asarray(camera, np.float32),
        "size": QUADRANT,
        "page_first": 0,
        "page_across": frame_grid(QUADRANT)[0],
    }


def depth_model(loop, scene, view):
    """The model's layout of the DEPTH view `view`: the layers a DEPTH view draws, in
    the frame's order, each seen by the view's camera."""
    _, host = names.threads_host(loop.loaded)
    held = names.capacity(host)
    given = names.numbers(host)
    layers = [
        (
            name,
            {**one, "camera": view["camera"], "size": view["size"]},
            shade,
        )
        for name, one, shade in tile_half.layers_of(loop, scene)
        if name in host.depth_layers
    ]
    if [name for name, _, _ in layers] != list(host.layers)[: len(layers)]:
        raise ValueError(f"the depth layers {layers} are not the frame's first ones")
    return laid_out(
        layers,
        view,
        held,
        given["heavy"],
        given["range_blocks"],
        None,
        None,
        host.held.wide,
    )


def run_sun(loop, scene, policy):
    """The hosts' views, the tile phase and `policy`, the SUN command: {code,
    standing (None unless it ended badly)}."""
    camera = np.asarray(scene["camera"], dtype=np.float32)
    try:
        for host in loop.hosts():
            hosted(host, "view")(loop.loaded, camera, loop.size)
        set_frame(loop, names.mask("tile"), policy)
        code = loop.loaded.serve(SUN, row=True)
    except (km.KomorebiError, TimeoutError) as error:
        stood = standing(loop.loaded, None, error)
        return {"code": None, "standing": stood | {"choice": handed(loop)}}
    if code:
        stood = standing(loop.loaded, code)
        return {"code": code, "standing": stood | {"choice": handed(loop)}}
    return {"code": 0, "standing": None}


def handed(loop):
    """The tile pull's choice as it stood (read after the stop): the records handed
    and held, each asking core's tells: {handed, records, tells}."""
    raw = np.frombuffer(loop.loaded.region(names.STATE), dtype=np.uint32)
    head_words, core_words = CHOOSE["DP_CHOOSE_HEAD_WORDS"], CHOOSE["DP_CORE_WORDS"]
    head = raw[:head_words]
    end = head_words + core_words * PORTS_CORES
    cores = raw[head_words:end].reshape(-1, core_words)
    slices = raw[end:].reshape(-1, CHOOSE["DP_SLICE_WORDS"])[: head[2]]
    next_ = np.minimum(slices[:, 1], slices[:, 0])
    return {
        "handed": int(next_.sum()),
        "records": int(slices[:, 0].sum()),
        "tells": {c: int(cores[c, 3]) for c in range(PORTS_CORES) if cores[c, 3]},
    }


def check(open_loop, threads_name, stage_name, scene, cores_list, policies, options):
    """The sun's DEPTH view of `scene` by `threads_name` against `stage_name`'s map at
    each count of cores (None: every core) and each policy: the record."""
    want = stagewise_map(open_loop, stage_name, scene, options)
    out = {"stagewise": {"preset": stage_name, "code": want["code"]}, "runs": {}}
    out["stagewise"]["nonzero_pages"] = int(want["map"].any(axis=1).sum())
    for cores in cores_list:
        loop = open_loop(threads_name, {**options, "cores": cores})
        ran = {}
        try:
            laid = depth_model(loop, scene, depth_view(loop))
            given = tile_half.written(loop, laid)
            for policy in policies:
                cleared(loop)
                done = run_sun(loop, scene, policy)
                one = {"code": done["code"], "standing": done["standing"]}
                if done["standing"] is None:
                    one |= judged(map_of(loop), want["map"])
                ran[policy] = one
                whole.say(f"cores {cores}, {policy}: {short(one)}")
                if done["standing"] is not None:
                    break
        finally:
            stop = closed(loop)
        out["runs"][str(cores or "all")] = {
            "written": given,
            "frames": ran,
            "stop": stop,
            "model": tile_half.summary(laid),
        }
    judged_all = [one for r in out["runs"].values() for one in r["frames"].values()]
    out["equal"] = bool(judged_all) and all(one.get("equal") for one in judged_all)
    return out


def short(one):
    """One line of a judged map."""
    if one.get("standing") is not None:
        stood = one["standing"]
        return f"ended badly ({stood['code']}, choice {stood.get('choice')})"
    if one.get("equal"):
        return "equal"
    return f"{one.get('bytes_differ')} bytes, {one.get('pages_differ')} pages differ"
