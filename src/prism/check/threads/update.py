"""The field's update in the threads' form: the stage-wise preset's frame after its
update (its picture, map, field pages, scale) at each deal of the transport's weights;
the threads' loop's commands sent, its update's graph waited for, the field it wrote
judged against each, then its frames after the update judged as the whole frame's."""

import komorebi as km
import numpy as np

from prism.check.threads import whole
from prism.check.threads.card import closed, set_frame
from prism.check.threads.standing import standing
from prism.check.threads.sun import map_of, shadow_host
from prism.core.implementation import command_of, hosted
from prism.program.threads.hosts import transport_of
from prism.stages.indirect.field_update.check import codes
from prism.stages.indirect.field_update.model.results import times

FIELD = "indirect.field_update"  # the field update's implementation


def field_host(loop):
    """The loaded run's host of the field's update."""
    return loop.loaded.hosts[FIELD]


def field_state(loop):
    """The field the light pages hold now: its pages, its scale, (sun, bounces), half."""
    host = field_host(loop)
    return {
        "pages": host.field_pages().copy(),
        "scale": host.given["scale"],
        "made": host.made,
        "half": host.half,
    }


def stagewise(open_loop, name, scene, options):
    """The stage-wise preset `name`'s first frame of `scene` (its SUN and update sent
    before it): {code, picture, map, field, sun passes}."""
    loop = open_loop(name, dict(options))
    try:
        frame = loop.frame(scene["camera"], picture=True)
        out = {"code": frame.code, "picture": frame.picture, "map": map_of(loop)}
        out |= {"field": field_state(loop), "passes": list(shadow_host(loop).passes)}
    finally:
        loop.stop()
    whole.say(
        f"{name} {options.get('cores') or 'all'} cores: code {out['code']}, sun "
        f"passes {out['passes']}, field {out['field']['made']}"
    )
    return out


def commands_sent(loop, camera):
    """The hosts' views, then the commands they ask for served in order as the loop
    serves them (no frame): [{command, code}], up to the first code that is not 0."""
    camera = np.asarray(camera, dtype=np.float32)
    for host in loop.hosts():
        hosted(host, "view")(loop.loaded, camera, loop.size)
    sent = []
    for host in loop.hosts():
        for asked in hosted(host, "commands")(loop.loaded):
            command = command_of(asked)
            code = loop.loaded.serve(command.name, command.args, command.row)
            hosted(host, "served")(loop.loaded, command.name, code)
            sent.append({"command": command.name, "code": code})
            if code:
                return sent
    return sent


def fields_judged(got, want):
    """Two fields' pages: the words that differ, each channel's largest code step, the
    scales."""
    differ = got["pages"] != want["pages"]
    steps = np.abs(
        codes(got["pages"].reshape(-1)).astype(np.int64)
        - codes(want["pages"].reshape(-1)).astype(np.int64)
    )
    return {
        "equal": not differ.any() and got["scale"] == want["scale"],
        "words_differ": int(differ.sum()),
        "words": int(differ.size),
        "nonzero_words": int((got["pages"] != 0).sum()),
        "largest_code_step": [int(step) for step in steps.max(axis=0)],
        "scale": [float(got["scale"] or 0.0), float(want["scale"] or 0.0)],
    }


def updated(loop, scene, policy):
    """The threads' loop's commands sent with `policy` set (the SUN served, the
    update's graph started), the graph waited for: {sent, started, served, field}."""
    set_frame(loop, 0, policy)
    sent = commands_sent(loop, scene["camera"])
    graph = field_host(loop).graph
    started = graph.handle is not None
    out = {"sent": sent, "started": started}
    try:
        served = graph.served(wait=True) if started else None
    except km.KomorebiError as error:
        return out | {"served": None, "standing": standing(loop.loaded, None, error)}
    if served is None:
        return out | {"served": None}
    code, scale = served
    out["served"] = {"code": code, "scale": float(scale)}
    return out | {"field": field_state(loop)}


def check(open_loop, threads_name, stage_name, scene, policies, options, sun, deals):
    """The update of `sun` in `threads_name` against `stage_name`'s at each deal of
    `deals` (the transport's cores; None every core), then the frames after it under
    each policy against the first deal's: the record."""
    wants = {
        str(deal or "all"): stagewise(
            open_loop, stage_name, scene, {**sun, "cores": deal}
        )
        for deal in deals
    }
    first = wants[str(deals[0] or "all")]
    out = {
        "stagewise": {
            key: {"code": want["code"], "sun_passes": want["passes"]}
            for key, want in wants.items()
        }
    }
    loop = open_loop(threads_name, {**options, **sun})
    out["update_cores"] = transport_of(loop.loaded.assembled)[1].cores
    whole.say(f"the update takes {out['update_cores']} cores")
    try:
        done = updated(loop, scene, policies[0])
        if "field" in done:
            done["judged"] = {
                key: fields_judged(done["field"], want["field"])
                for key, want in wants.items()
            }
            done["field"] = {k: v for k, v in done["field"].items() if k != "pages"}
            whole.say(f"update: {done['served']}, field {short(done['judged'])}")
            count = whole.loop_cores(loop)
            done["frames"] = whole.frames(
                loop, scene, first["picture"], policies, count, 0, first["map"]
            )
        else:
            whole.say(f"update: not served ({done})")
    finally:
        stop = closed(loop)
    done["stop"] = stop
    done["times"] = rows_of(field_host(loop).graph.times())
    out["update"] = done
    frames = done.get("frames", {})
    out["equal"] = bool(frames) and all(one.get("equal") for one in frames.values())
    return out


def rows_of(raw):
    """The job thread's times rows as told apart (no durations): number, code, passes,
    the parts it holds."""
    return [
        {"number": row.get("number"), "code": row.get("code"), "passes": row["passes"]}
        | {"parts": sorted(k for k, v in row.items() if isinstance(v, float) and v)}
        for row in times(raw)
    ]


def short(judged):
    """One line of the fields judged by deal."""
    return "; ".join(
        f"{key}: {'equal' if one['equal'] else str(one['words_differ']) + ' words'}"
        f" (steps {one['largest_code_step']})"
        for key, one in judged.items()
    )
