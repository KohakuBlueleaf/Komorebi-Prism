"""The account of frames of a loaded loop: the frames run, each frame's profile pages
and directories read after it, the trace read after the stop, and the record: the
times, each command's cores, spread, bytes, counts and closure, the L1 and the code."""

import datetime
import subprocess
from pathlib import Path

import komorebi as km
import numpy as np
from komorebi.bench import power

from prism.check.account.code import code_sizes, l1_rows
from prism.check.account.commands import frame_commands, segments
from prism.check.account.moved import directory, moved
from prism.check.account.profiles import words_of
from prism.check.account.terms import accounted, cpus_of
from prism.check.harness import card_of, pcie_link
from prism.loop.report import by_name
from prism_reference.scene.camera import with_size
from prism_reference.scene.frame import frame_grid

RASTER, TEXTURE, LIGHT, SHOW = "raster", "material.texture", "direct.light", "post.show"
LIGHT_FORMS = {"light": "opaque", "light_glass": "glass"}
MS = 1e-3  # a microsecond's
DIGITS = 4


def read_frame(loaded, layers):
    """A frame's profile pages and directories by command kind and layer, read after
    its event."""
    session, hosts = loaded.session, loaded.hosts
    raster, texture = hosts[RASTER], hosts.get(TEXTURE)
    out = {"passes": {}, "fill": {}, "directory": {}, "shade": {}, "light": {}}
    for name in layers:
        own = raster.layers[name]
        out["passes"][name] = words_of(session, own["profile"])
        out["fill"][name] = words_of(session, own["fill_profile"])
        out["directory"][name] = directory(words_of(session, own["directory"]))
        if texture is not None and name in texture.layers:
            out["shade"][name] = words_of(session, texture.layers[name]["profile"])
    light = hosts.get(LIGHT)
    for form, layer in LIGHT_FORMS.items():
        if light is not None and layer in light.own:
            out["light"][form] = words_of(session, light.own[layer]["profile"])
    show = hosts.get(SHOW)
    out["show"] = None if show is None else words_of(session, show.tensors["profile"])
    return out


def frame_facts(loop, layers, sample, row):
    """What moved() needs of a frame besides its profiles."""
    raster = loop.loaded.hosts[RASTER]
    across, down = frame_grid(loop.size)
    heavy = row.get("heavy_tiles", [0] * len(layers))
    lit = getattr(loop.loaded.hosts.get(TEXTURE), "lights", None) is not None
    return {
        "cores": raster.cores,
        "tiles": across * down,
        "grid": (across, down),
        "held": raster.held,
        "heavy": heavy if isinstance(heavy, list) else [heavy],
        "directories": sample["directory"],
        "merging": {"masked"} if lit else set(),
        "first": layers[0],
        "glass": "glass",
    }


def komorebi_commit():
    """Komorebi's commit when it runs from a checkout, else None."""
    try:
        return subprocess.run(
            [
                "git",
                "-C",
                str(Path(km.__file__).parent),
                "rev-parse",
                "--short",
                "HEAD",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def median_of(values):
    """The median over frames of numbers, arrays (a core each) or dicts of them."""
    first = values[0]
    if isinstance(first, dict):
        return {key: median_of([one[key] for one in values]) for key in first}
    if isinstance(first, np.ndarray):
        return np.median(np.stack(values), axis=0)
    if first is None:
        return None
    return float(np.median(values))


def rounded_ms(cycles, mhz):
    """Cycles at `mhz` as ms, rounded, a list a core."""
    return np.round(cycles / mhz * MS, DIGITS).tolist()


def in_ms(cpus, mhz):
    """CPUs' cycles (busy steps, waits, total) in ms, a list a core."""
    return {
        name: {
            "busy": {step: rounded_ms(v, mhz) for step, v in cpu["busy"].items()},
            "wait": {kind: rounded_ms(v, mhz) for kind, v in cpu["wait"].items()},
            "total": rounded_ms(cpu["total"], mhz),
        }
        for name, cpu in cpus.items()
    }


def counts_of(cpus, sample, command, first):
    """The command's counts a core: its profile's, and for a command that walks a
    directory its items and rows (`first` the first layer's name)."""
    out = {}
    for cpu in (cpus or {}).values():
        out |= {name: v.astype(float) for name, v in cpu["counts"].items()}
    if command.name in ("fill", "shade", "light", "light_glass", "show"):
        glass = command.name == "light_glass"
        layer = LIGHT_FORMS[command.name] if glass else command.layer_name or first
        walked = sample["directory"][layer]
        out["directory_items"] = walked["items"].astype(float)
        out["directory_rows"] = walked["rows"].astype(float)
    return out


def command_sample(command, row, sample, facts, rows, index, mhz):
    """One frame's account of `command`: its time, CPUs, counts, bytes and terms."""
    command_us = row[command.name]
    if isinstance(command_us, list):
        command_us = command_us[command.layer]
    cpus = cpus_of(command, sample) if command.cores else None
    read, written = moved(command, cpus or {}, facts) if command.cores else ({}, {})
    terms = None
    if command.cores and rows is not None and index is not None:
        terms = accounted(command_us, cpus, rows, index, mhz)
    return {
        "command_ms": command_us * MS,
        "cpus": cpus,
        "counts": counts_of(cpus, sample, command, facts["first"]),
        "read": read,
        "written": written,
        "terms": terms,
    }


def gbs(moved_bytes, command_ms):
    """Bytes over a command's time as GB/s."""
    return round(sum(moved_bytes.values()) / (command_ms * MS) / 1e9, DIGITS)


def stage_record(command, samples, mhz):
    """A command's record from its frames' samples: medians over the frames."""
    command_ms = median_of([s["command_ms"] for s in samples])
    out = {"command": command.name, "layer": command.layer_name}
    out["command_ms"] = round(command_ms, DIGITS)
    if not command.cores:
        out["cores"] = None
        return out
    cpus = [s["cpus"] for s in samples if s["cpus"] is not None]
    if cpus:
        out["cores"] = in_ms(
            {
                name: {
                    "busy": median_of([one[name]["busy"] for one in cpus]),
                    "wait": median_of([one[name]["wait"] for one in cpus]),
                    "total": median_of([one[name]["total"] for one in cpus]),
                }
                for name in cpus[0]
            },
            mhz,
        )
    else:
        out["cores"] = None
    terms = [s["terms"] for s in samples if s["terms"] is not None]
    if terms:
        out["busy_from"] = terms[0]["busy_from"]
        out["spread"] = rounded(median_of([t["spread"] for t in terms]))
        out["terms_ms"] = rounded(median_of([t["terms"] for t in terms]))
        out["closure"] = rounded(median_of([t["ratio"] for t in terms]))
    read = median_of([s["read"] for s in samples]) if samples[0]["read"] else {}
    written = (
        median_of([s["written"] for s in samples]) if samples[0]["written"] else {}
    )
    out["moved"] = {
        "read": {k: int(v) for k, v in read.items()},
        "written": {k: int(v) for k, v in written.items()},
        "read_gbs": gbs(read, command_ms),
        "written_gbs": gbs(written, command_ms),
    }
    counts = median_of([s["counts"] for s in samples]) if samples[0]["counts"] else {}
    out["items"] = {name: np.round(v, 1).tolist() for name, v in counts.items()}
    return out


def rounded(value):
    """Floats and dicts of them rounded to DIGITS."""
    if isinstance(value, dict):
        return {key: rounded(one) for key, one in value.items()}
    return None if value is None else round(float(value), DIGITS)


def frame_medians(rows):
    """The median of every times column over `rows` (a layer unit's by layer), in ms;
    the result columns of the last row."""
    flat = [by_name(row, list(row)) for row in rows]
    out = {}
    for name in flat[-1]:
        values = [one[name] for one in flat if name in one]
        out[name] = round(float(np.median(values)) * MS, DIGITS)
    return out


def account(loop, frames):
    """`frames` frames of the loaded `loop` at its view's camera (its option `trace`
    the trace kept), the loop stopped after them; the account's record."""
    loaded = loop.loaded
    card = card_of(loaded)
    clock = [power.aiclk_mhz(card)]
    link = [pcie_link(card)]
    layers = list(loaded.hosts[RASTER].layers)
    camera = with_size(loop.scene, loop.size)["camera"]
    samples, codes, numbers = [], [], []
    set_up = loaded.served == 0  # the load's first frame sets the units up
    for _ in range(frames):
        frame = loop.frame(camera)
        codes.append(frame.code)
        numbers.append(frame.row)
        if frame.code:
            break
        samples.append(read_frame(loaded, layers))
    clock.append(power.aiclk_mhz(card))
    link.append(pcie_link(card))
    trace_cap = int(loaded.options.get("trace") or 0)
    loop.stop()
    rows = [loop.times()[n] for n in numbers[: len(samples)]]
    trace = loaded.run.trace() if trace_cap else None
    mhz = trace.mhz if trace is not None else clock[0]
    times_columns, result_columns = list(loaded.layout.times), list(
        loaded.layout.results
    )
    commands = [frame_commands(row, layers) for row in rows]
    core_counts = [sum(c.cores for c in one) for one in commands]
    found = segments(trace.rows, core_counts, set_up) if trace is not None else None
    by_key, order = {}, []
    for number, (row, sample) in enumerate(zip(rows, samples, strict=True)):
        facts = frame_facts(loop, layers, sample, row)
        indices = iter(found[number] or []) if found else iter(())
        for command in commands[number]:
            index = next(indices, None) if command.cores else None
            if command.key not in by_key:
                by_key[command.key], order = (command, []), order + [command.key]
            by_key[command.key][1].append(
                command_sample(command, row, sample, facts, trace and trace.rows,
                               index, mhz)
            )  # fmt: skip
    stages = [stage_record(*by_key[key], mhz) for key in order]
    sums = [
        row["frame"]
        - sum(
            (row[c.name][c.layer] if isinstance(row[c.name], list) else row[c.name])
            for c in one
        )
        for row, one in zip(rows, commands, strict=True)
    ]
    times = frame_medians([{k: r[k] for k in times_columns} for r in rows])
    return {
        "case": {
            "pipeline": loaded.assembled.pipeline.name,
            "size": list(loop.size),
            "frames": len(codes),
            "card": card,
            "aiclk_mhz": clock,
            "pcie_link": link,
            "date": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "komorebi": {"version": km.__version__, "commit": komorebi_commit()},
            "trace": trace_cap,
            "layers": layers,
        },
        "codes": codes,
        "frames_traced": sum(one is not None for one in found) if found else 0,
        "trace_frames": [one and [one[0] + 1, len(one)] for one in found or []],
        "frame_ms": times,
        "results": {k: rows[-1][k] for k in result_columns} if rows else {},
        "stages": stages,
        "thread_ms": round(float(np.median(sums)) * MS, DIGITS) if sums else None,
        "l1": l1_rows(loaded, trace_cap),
        "code": code_sizes(loaded),
        "closure": {
            f"{s['command']}.{s['layer']}" if s["layer"] else s["command"]: s.get(
                "closure"
            )
            for s in stages
        },
    }
