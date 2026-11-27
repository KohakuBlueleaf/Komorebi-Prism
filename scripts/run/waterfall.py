"""The waterfall of one frame of a threads' preset, drawn from the account's records
(the files of scripts/run/threads_account.py run with --account N, and --trace N for
the commands): a row a core by rank, a bar a thread coloured by kind (count, place, a
tile thread's steps), the sums and other commands from the trace, the X280 frame's
phases with its answers by port, one time axis in ms; an SVG to --out, the frame's
table by phase as one JSON line (and as Markdown to --table). No card. Example: python
scripts/run/waterfall.py R.json --out frame.svg
"""

import argparse
import json
import sys
from html import escape
from itertools import pairwise
from pathlib import Path

import numpy as np

from prism.program.frame.generate import FRAME
from prism.program.threads import tiles

WRAP = 1 << 32
X280_MHZ = 50.0  # the X280 timer the choice's ticks count
PULLS = {1: "count", 2: "place", 3: "tile"}  # answer.h TP_*
NEAR_SEQ = 16  # commands of other sources kept from this many before the count pull
PORTS = 4  # the frame cluster's X280 cores, a quarter of the ranks each
STEP_AT = 1 + FRAME["FX_R_STEPS"]  # a record row: its core first, then its words
R = {name: 1 + FRAME[f"FX_R_{name.upper()}"] for name in ("view", "number")}
R |= {k: 1 + FRAME[f"FX_R_{k.upper()}"] for k in ("asked", "taken", "start")}
R |= {"end_a": 1 + FRAME["FX_R_END_A"], "end_b": 1 + FRAME["FX_R_END_B"]}
PHASES = ("count", "sums", "place", "tile")
COLOURS = {  # class: (light, dark, label)
    "count": ("#3567c4", "#6f9be8", "count"),
    "place": ("#d08a1c", "#e8ab4f", "place"),
    "sums": ("#7a5bb5", "#a58ad8", "sums"),
    "visibility": ("#2a9d8f", "#4fc4b5", "visibility"),
    "material": ("#b8487e", "#da78a8", "material"),
    "material_lit": ("#b8487e", "#da78a8", "material"),
    "light": ("#e06c4f", "#f0927a", "light"),
    "post": ("#6f9a4a", "#98c46f", "post"),
    "depth_out": ("#5b6470", "#8e98a4", "depth out"),
    "asked": ("#c9c4bb", "#55524d", "asked, not answered"),
    "other": ("#8c8c8c", "#a8a8a8", "other command (job's applies)"),
    "x280": ("#4a4f9c", "#8389d6", "X280 phase"),
    "running": ("#9a6fd0", "#bb98e8", "running sum, words"),
}


def parse():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("record", type=Path, help="threads_account.py's --out file")
    parser.add_argument("--frame", type=int, default=None, help="from 0 (the last)")
    parser.add_argument(
        "--view", type=int, default=0, help="0 the eye's, 1 on the sun's"
    )
    parser.add_argument("--out", type=Path, required=True, help="the SVG")
    parser.add_argument("--table", type=Path, default=None, help="the table (.md)")
    parser.add_argument("--width", type=int, default=1600, help="the time axis, px")
    parser.add_argument("--note", default="", help="a line under the title")
    return parser.parse_args()


def loaded(path, frame):
    """The record, the frame's index, its records [n, 17] and the trace (or None)."""
    record = json.loads(path.read_text())
    held = np.load(path.with_suffix(".records.npz"))
    count = sum(key.startswith("frame_") for key in held.files)
    if not count:
        raise SystemExit(f"{path}: no records (run with --account N)")
    frame = count - 1 if frame is None else frame
    if not 0 <= frame < count:
        raise SystemExit(f"frame {frame}: the record holds 0 to {count - 1}")
    trace = held["trace"] if "trace" in held.files else None
    return record, frame, held[f"frame_{frame}"].astype(np.int64), trace


def signed(words, origin):
    """32-bit wall clock words as signed cycles after `origin`."""
    return (np.asarray(words, np.int64) - origin + WRAP // 2) % WRAP - WRAP // 2


def step_names(preset, kind):
    """The tile thread's step names of a view of `kind` (TV_DEPTH 1 at bit 8)."""
    thread = tiles.TEXTURED if preset.startswith("textured") else tiles.LIT
    steps = thread.depth() if kind else thread.colour()
    return [step.name for step in steps]


def threads_of(rows, origin, mhz, preset):
    """Each record as a thread: core, pull, view, asked, taken, start, end, its steps
    [(name, start, end)] (us after `origin`), sorted by core, pull and ask."""
    us = 1.0 / mhz
    out = []
    for row in rows:
        word = int(row[R["view"]])
        t = {
            k: float(signed(row[R[k]], origin)) * us
            for k in ("asked", "taken", "start")
        }
        ends = [float(signed(row[R[k]], origin)) * us for k in ("end_a", "end_b")]
        one = {"core": int(row[0]), "pull": PULLS.get(word >> 16, "?")}
        one |= {"view": word & 0xFF, "depth": (word >> 8) & 1, **t, "steps": []}
        if one["pull"] == "tile":
            names = step_names(preset, one["depth"])
            marks = [
                (n, float(signed(row[STEP_AT + i], origin)) * us)
                for i, n in enumerate(names)
                if row[STEP_AT + i]
            ]
            one["steps"] = marks
            one["end"] = max([ends[1], *(m for _, m in marks)])
        else:
            one["end"] = max(ends)
        out.append(one)
    out.sort(
        key=lambda o: (o["core"], list(PULLS.values()).index(o["pull"]), o["asked"])
    )
    return out


def segments(threads):
    """{core: [(start, end, class)]}: each thread's time on its core after the one
    before it on that core (a tile thread by its steps; its `begin` set), and the wait
    from its ask to its answer where the core had nothing running."""
    out = {}
    last = {}
    for t in threads:
        core = out.setdefault(t["core"], [])
        key = (t["core"], t["pull"], t["view"])
        before = last.get(key, -np.inf)
        begin = max(t["start"], before)
        t["begin"] = begin
        if t["taken"] > before:
            core.append((max(t["asked"], before), t["taken"], "asked"))
        if t["pull"] == "tile" and t["steps"]:
            at = begin
            for name, end in t["steps"]:
                core.append((at, max(at, end), name))
                at = max(at, end)
            last[key] = at
        else:
            core.append((begin, t["end"], t["pull"]))
            last[key] = t["end"]
    return out


def commands(trace, origin, mhz, threads, window):
    """The trace's commands inside `window` (us): [{seq, kind, cores [(core, seen,
    done)]}]; a command holding a pull's threads is that pull's, the one between the
    count and place pulls on the count's cores the sums, any other 'other'."""
    if trace is None:
        return []
    us = 1.0 / mhz
    out = []
    by_pull = {}
    for t in threads:
        by_pull.setdefault(t["pull"], []).append(t["start"])
    for seq in np.nonzero((trace[:, :, 0] != 0).any(axis=0))[0]:
        used = np.nonzero(trace[:, seq, 0])[0]
        seen = signed(trace[used, seq, 0], origin) * us
        done = signed(trace[used, seq, 1], origin) * us
        if done.max() < window[0] or seen.min() > window[1]:
            continue
        kind = "other"
        for pull, starts in by_pull.items():
            inside = [(seen.min() <= s <= done.max()) for s in starts[:64]]
            if starts and np.mean(inside) > 0.5:
                kind = pull
        cores = list(zip(used.tolist(), seen.tolist(), done.tolist(), strict=True))
        out.append({"seq": int(seq), "kind": kind, "cores": cores})
    pulls = {c["kind"]: c for c in out if c["kind"] in PULLS.values()}  # the latest
    if "count" in pulls:  # a slot of an older frame whose clock turned over: dropped
        least = pulls["count"]["seq"] - NEAR_SEQ
        out = [c for c in out if c["seq"] >= least and c["kind"] not in pulls]
        out = sorted(out + list(pulls.values()), key=lambda c: c["seq"])
    if "count" in pulls and "place" in pulls:
        for c in out:
            between = pulls["count"]["seq"] < c["seq"] < pulls["place"]["seq"]
            group = [one[0] for one in c["cores"]] == [
                one[0] for one in pulls["count"]["cores"]
            ]
            if c["kind"] == "other" and between and group:
                c["kind"] = "sums"
    return out


def overlap(segs, lo, hi, classes):
    """The time of `segs` of `classes` inside [lo, hi]."""
    return sum(max(0.0, min(e, hi) - max(s, lo)) for s, e, c in segs if c in classes)


def table(threads, segs, cmds, row, choice_ticks, last):
    """Each phase: its window (ms), its cores, core-ms working and standing still (and
    of it, asked and not answered), the longest thread (ms), the X280's share."""
    out = {}
    steps = {c for t in threads for c, _ in t["steps"]}
    classes = {"count": {"count"}, "place": {"place"}, "tile": steps, "sums": {"sums"}}
    x280 = {"count": "dispatch_count", "sums": "dispatch_sums"}
    x280 |= {"place": "dispatch_place", "tile": "dispatch_tile"}
    for phase in PHASES:
        cmd = next((c for c in cmds if c["kind"] == phase), None)
        mine = [t for t in threads if t["pull"] == phase]
        if cmd is not None:
            cores = [c for c, _, _ in cmd["cores"]]
            lo = min(s for _, s, _ in cmd["cores"])
            hi = max(e for _, _, e in cmd["cores"])
        elif mine:
            cores = sorted({t["core"] for t in mine})
            lo, hi = min(t["asked"] for t in mine), max(t["end"] for t in mine)
        else:
            continue
        span = hi - lo
        if phase == "sums":
            work = sum(e - s for _, s, e in cmd["cores"])
            longest = max(e - s for _, s, e in cmd["cores"])
            asked = 0.0
        else:
            work = sum(overlap(segs.get(c, []), lo, hi, classes[phase]) for c in cores)
            asked = sum(overlap(segs.get(c, []), lo, hi, {"asked"}) for c in cores)
            longest = max(t["end"] - t["begin"] for t in mine)
        one = {"from_ms": lo / 1e3, "span_ms": span / 1e3, "cores": len(cores)}
        one |= {"working_core_ms": work / 1e3}
        one |= {"standing_core_ms": (span * len(cores) - work) / 1e3}
        one |= {"asked_core_ms": asked / 1e3, "longest_ms": longest / 1e3}
        one["threads"] = len(mine)
        one["x280_ms"] = row.get(x280[phase])
        if phase == "tile" and choice_ticks is not None and last:
            choosing = choice_ticks / X280_MHZ / 1e3
            one["x280_choosing_ms"] = choosing
            one["x280_busy_share"] = choosing / one["x280_ms"]
        else:
            one["x280_busy_share"] = None
        out[phase] = one
    windows = sorted((o["from_ms"], o["from_ms"] + o["span_ms"]) for o in out.values())
    gaps = [max(0.0, b[0] - a[1]) for a, b in pairwise(windows)]
    if gaps:
        cores = max(o["cores"] for o in out.values())
        running = row.get("dispatch_running", 0.0) + row.get("dispatch_words", 0.0)
        out["between"] = {
            "from_ms": None,
            "span_ms": sum(gaps),
            "cores": cores,
            "threads": 0,
            "working_core_ms": 0.0,
            "standing_core_ms": sum(gaps) * cores,
            "asked_core_ms": 0.0,
            "longest_ms": max(gaps),
            "x280_ms": running,
            "x280_busy_share": None,
        }
    return out


def x280_phases(row, threads, cmds):
    """The X280 frame's phases placed on the cores' axis (us): count, place and tile
    end at their last thread's end; the sums (with the running sum) follow the count,
    the steps' words end at the tile pull's first ask."""
    ends = {}
    for t in threads:
        ends[t["pull"]] = max(ends.get(t["pull"], -np.inf), t["end"])
    firsts = {}
    for t in threads:
        firsts[t["pull"]] = min(firsts.get(t["pull"], np.inf), t["asked"])
    out = []
    ms = {k: row.get(f"dispatch_{k}", 0.0) * 1e3 for k in ("count", "sums", "running")}
    ms |= {k: row.get(f"dispatch_{k}", 0.0) * 1e3 for k in ("place", "words", "tile")}
    for pull in ("count", "place", "tile"):
        if pull in ends:
            out.append((ends[pull] - ms[pull], ends[pull], "x280", pull))
    if "count" in ends:
        at = ends["count"]
        out.append((at, at + ms["sums"] - ms["running"], "x280", "sums"))
        out.append((at + ms["sums"] - ms["running"], at + ms["sums"], "running", ""))
    if "tile" in firsts:
        out.append((firsts["tile"] - ms["words"], firsts["tile"], "running", ""))
    return out


def style():
    """The SVG's classes, light and dark."""
    light = "".join(f".{k}{{fill:{v[0]}}}" for k, v in COLOURS.items())
    dark = "".join(f".{k}{{fill:{v[1]}}}" for k, v in COLOURS.items())
    base = (
        "svg{background:#fbf8f3}text{font:11px sans-serif;fill:#2b2723}"
        ".axis{stroke:#cfc8bd;stroke-width:1}.band{fill:#efe9df}"
    )
    night = (
        "svg{background:#1f1d1b}text{fill:#e9e3d9}.axis{stroke:#4a4640}"
        ".band{fill:#2a2724}"
    )
    return f"{base}{light}@media (prefers-color-scheme: dark){{{night}{dark}}}"


def merged(segs, span, width):
    """`segs` as pixel runs [(px0, px1, class, opacity)]: each pixel the class that
    covers most of it, its opacity the share of the pixel that class's group covers
    (working or asked; in quarters), a pixel covered less than a tenth left empty."""
    per = span / width
    cover = {}
    for s, e, c in segs:
        lo, hi = max(s, 0.0) / per, min(e, span) / per
        if hi <= lo:
            continue
        row = cover.setdefault(c, np.zeros(width + 1))
        first, last = int(lo), min(int(hi), width)
        if first == last:
            row[first] += hi - lo
            continue
        row[first] += first + 1 - lo
        row[first + 1 : last] += 1.0
        row[last] += hi - last
    if not cover:
        return []
    names = list(cover)
    stack = np.stack([cover[n][:width] for n in names])
    total = stack.sum(axis=0)
    work = stack[[n != "asked" for n in names]].sum(axis=0)
    top = stack.argmax(axis=0)
    runs = []
    for px in range(width):
        if total[px] < 0.1:
            continue
        name = names[top[px]]
        share = stack[top[px], px] if name == "asked" else work[px]
        alpha = max(0.25, round(min(share, 1.0) * 4) / 4)
        if runs and runs[-1][1] == px and runs[-1][2:] == (name, alpha):
            runs[-1] = (runs[-1][0], px + 1, name, alpha)
        else:
            runs.append((px, px + 1, name, alpha))
    return runs


def rect(x0, x1, y, h, cls):
    w = max(x1 - x0, 0.35)
    return (
        f'<rect x="{x0:.2f}" y="{y:.1f}" width="{w:.2f}" height="{h}" class="{cls}"/>'
    )


def svg(title, note, segs, cmds, phases, answers, span, cores, width, tab):
    """The waterfall's SVG text."""
    left, top, row_h, strip_h = 64, 64, 4, 7

    def x(t):
        return left + (t / span) * width

    x280_y = top + 4
    job_y = x280_y + 18
    ports_y = job_y + 16
    cores_y = ports_y + PORTS * (strip_h + 1) + 16
    height = cores_y + cores * row_h + 70
    out = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{left + width + 24}" '
            f'height="{height}" viewBox="0 0 {left + width + 24} {height}">'
        ),
        f"<style>{style()}</style>",
        (
            f'<text x="{left}" y="20" style="font-size:14px;font-weight:600">'
            f"{escape(title)}</text>"
        ),
        f'<text x="{left}" y="38">{escape(note)}</text>',
    ]
    label_end = -1e9
    for phase, one in tab.items():
        if one["from_ms"] is None:
            continue
        lo, hi = one["from_ms"] * 1e3, (one["from_ms"] + one["span_ms"]) * 1e3
        out.append(rect(x(lo), x(hi), cores_y, cores * row_h, "band"))
        at = max(x(lo) + 2, label_end + 6)
        out.append(
            f'<text x="{at:.1f}" y="{cores_y + cores * row_h + 14}">{phase}</text>'
        )
        label_end = at + 6.5 * len(phase)
    out.append(f'<text x="4" y="{x280_y + 10}">X280 1</text>')
    for s, e, cls, label in phases:
        out.append(rect(x(s), x(e), x280_y, 14, cls))
        if label and x(e) - x(s) > 30:
            out.append(
                f'<text x="{x(s) + 3:.1f}" y="{x280_y + 11}" style="fill:#fff">'
                f"{label}</text>"
            )
    out.append(f'<text x="4" y="{job_y + 9}">X280 2, 3</text>')
    jobs = [c for c in cmds if c["kind"] == "other"]
    for c in jobs:
        lo = min(s for _, s, _ in c["cores"])
        out.append(rect(x(lo), x(max(e for _, _, e in c["cores"])), job_y, 10, "other"))
    group = next((c["cores"] for c in cmds if c["kind"] == "count"), [])
    held = sorted(set(range(cores)) - {one[0] for one in group}) if group else []
    if not jobs:
        say = "no apply in the frame"
        if held:
            say += f"; ranks {held[0]} to {held[-1]} held for the field's update"
        out.append(f'<text x="{left + 2}" y="{job_y + 9}">job thread: {say}</text>')
    out.append(f'<text x="4" y="{ports_y + 12}">answers</text>')
    for port, counts in enumerate(answers):
        y = ports_y + port * (strip_h + 1)
        peak = max(counts.max(), 1)
        for px in np.nonzero(counts)[0]:
            alpha = 0.15 + 0.85 * counts[px] / peak
            out.append(
                f'<rect x="{left + px}" y="{y}" width="1" height="{strip_h}" '
                f'class="x280" style="opacity:{alpha:.2f}"/>'
            )
    out.append(f'<text x="4" y="{cores_y + 8}">core 0</text>')
    out.append(f'<text x="4" y="{cores_y + cores * row_h}">core {cores - 1}</text>')
    others = {}
    for c in cmds:
        if c["kind"] in ("sums", "other"):
            for core, s, e in c["cores"]:
                others.setdefault(core, []).append((s, e, c["kind"]))
    for core in range(cores):
        y = cores_y + core * row_h
        mine = segs.get(core, []) + others.get(core, [])
        for x0, x1, cls, alpha in merged(mine, span, width):
            shade = "" if alpha == 1 else f' style="opacity:{alpha:g}"'
            out.append(
                f'<rect x="{left + x0}" y="{y}" width="{x1 - x0}" height="{row_h - 1}" '
                f'class="{cls}"{shade}/>'
            )
    axis_y = cores_y + cores * row_h + 24
    step = next(s for s in (0.5, 1, 2, 5, 10, 20, 50) if span / 1e3 / s <= 12)
    out.append(
        f'<line x1="{left}" x2="{left + width}" y1="{axis_y}" y2="{axis_y}" class="axis"/>'
    )
    t = 0.0
    while t <= span / 1e3 + 1e-9:
        px = x(t * 1e3)
        out.append(
            f'<line x1="{px:.1f}" x2="{px:.1f}" y1="{top}" y2="{axis_y}" class="axis" style="opacity:0.35"/>'
        )
        out.append(f'<text x="{px - 6:.1f}" y="{axis_y + 14}">{t:g}</text>')
        t += step
    out.append(f'<text x="{left + width - 20}" y="{axis_y + 28}">ms</text>')
    shown = ("count", "sums", "place", "visibility", "material", "light", "post")
    shown += ("asked", "other", "x280", "running")
    lx = left
    for key in shown:
        label = COLOURS[key][2]
        out.append(rect(lx, lx + 10, 46, 9, key))
        out.append(f'<text x="{lx + 13}" y="{55}">{escape(label)}</text>')
        lx += 22 + 6.2 * len(label)
    out.append("</svg>")
    return "\n".join(out) + "\n"


def answered(threads, span, width):
    """The answers by port, a count a pixel of the time axis."""
    out = np.zeros((PORTS, width), np.int64)
    per = None
    for t in threads:
        per = per or max(1, (max(o["core"] for o in threads) + PORTS) // PORTS)
        px = int(t["taken"] / span * width)
        if 0 <= px < width:
            out[min(t["core"] // per, PORTS - 1), px] += 1
    return out


def markdown(name, tab, frame_ms):
    """The table as Markdown."""
    lines = [
        f"{name}: frame {frame_ms:.3f} ms (X280's times row)",
        "",
        (
            "| phase | span ms | cores | threads | core-ms working | core-ms standing "
            "(asked) | longest ms | X280 ms | X280 busy share |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for phase, o in tab.items():
        share = "-" if o["x280_busy_share"] is None else f"{o['x280_busy_share']:.0%}"
        lines.append(
            f"| {phase} | {o['span_ms']:.3f} | {o['cores']} | {o['threads']} | "
            f"{o['working_core_ms']:.1f} | {o['standing_core_ms']:.1f} "
            f"({o['asked_core_ms']:.1f}) | {o['longest_ms']:.3f} | "
            f"{o['x280_ms'] or 0:.3f} | {share} |"
        )
    return "\n".join(lines) + "\n"


def main():
    args = parse()
    record, frame, rows, trace = loaded(args.record, args.frame)
    rows = rows[(rows[:, R["view"]] & 0xFF) == args.view]
    if not len(rows):
        raise SystemExit(f"frame {frame}: no record of view {args.view}")
    case = record["case"]
    mhz = record.get("trace_mhz") or case["aiclk_mhz"][0]
    asks = rows[:, R["asked"]]
    origin = int(asks[np.argmin(signed(asks, asks[0]))])
    for _ in range(2):  # the axis from the view's first pull taken, else its first ask
        threads = threads_of(rows, origin, mhz, case["preset"])
        end = max(t["end"] for t in threads)
        cmds = commands(trace, origin, mhz, threads, (-1e3, end + 50))
        first = [c for c in cmds if c["kind"] in PULLS.values()][:1]
        begin = min([0.0] + [s for c in first for _, s, _ in c["cores"]])
        origin += round(begin * mhz)
    cmds = [c for c in cmds if min(s for _, s, _ in c["cores"]) >= 0]
    segs = segments(threads)
    row = record["rows"][frame]
    ticks = record.get("choice", {}).get("ticks")
    last = frame == len(record["rows"]) - 1
    tab = table(threads, segs, cmds, row, None if ticks is None else sum(ticks), last)
    span = max(t["end"] for t in threads) * 1.01
    cores = 1 + max(t["core"] for t in threads)
    lost = record.get("account", [{}])[frame].get("lost")
    title = (
        f"{case['scene']} ({case['view']}), {case['preset']} {case['way']}, "
        f"{case['size'][0]} x {case['size'][1]}, frame {frame + 1} of "
        f"{len(record['rows'])}: {row['frame']:.3f} ms"
    )
    if lost:
        title += f" ({lost} records lost: threads missing)"
    note = (
        f"AICLK {case['aiclk_mhz'][0]} MHz, Komorebi {case['komorebi']}, "
        f"{case['date'][:10]}, records lost {lost}. {args.note}"
    )
    text = svg(
        title,
        note,
        segs,
        cmds,
        x280_phases(row, threads, cmds),
        answered(threads, span, args.width),
        span,
        cores,
        args.width,
        tab,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text)
    if args.table:
        args.table.write_text(markdown(title, tab, row["frame"]))
    print(json.dumps({"frame": frame, "frame_ms": row["frame"], "phases": tab}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
