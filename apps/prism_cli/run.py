"""`run`: a preset's Loop on one card, its frames along a camera path, the checked
pictures against the preset's REFERENCE and by its JUDGE, the record as one JSON line
(and into --out through the harness); 1 on a frame code that is not 0."""

import json
import time

import komorebi as km
import numpy as np

from prism.check import harness
from prism.loop import path, report
from prism_cli.preset import opened
from prism_reference.scene.camera import sized_camera, with_size

MS = 1e-3  # a microsecond's


def differ(got, want):
    """Pixels whose planes (or a display picture's four bytes) are not the
    reference's bit for bit; None without one."""
    if got is None or want is None:
        return None
    if got.dtype == np.uint8:
        return int((got[..., :3] != want[..., :3]).any(axis=2).sum())
    return int((got.view(np.uint32) != want.view(np.uint32)).any(axis=0).sum())


def host_figures(host):
    """Each frame's host ms (the frame and its picture): the median, the least, and the
    frames a second of the median."""
    if not host:
        return {}
    median = float(np.median(host))
    return {"median": round(median, 3), "least": round(min(host), 3)} | {
        "fps": round(1e3 / median, 2)
    }


def layer_sums(loop, frames):
    """Each time column a layer unit gives by layer, summed over its layers in a row:
    the median and the least of the sums over the frames asked for, in ms."""
    rows = loop.times()
    rows = [rows[frame.row] for frame in frames if 0 <= frame.row < len(rows)]
    rows = [row for row in rows if row is not None]
    out = {}
    for name in report.columns(loop)[0]:
        sums = [sum(row[name]) for row in rows if isinstance(row[name], list)]
        if sums:
            values = np.array(sums, dtype=np.float64) * MS
            out[name] = {
                "median": round(float(np.median(values)), 4),
                "least": round(float(values.min()), 4),
            }
    return out


def judged(preset, loop, pictures):
    """The checked pictures against the preset's REFERENCE (pixels that differ, bit for
    bit) and by its JUDGE (its numbers), by frame."""
    out = {}
    for index, (got, view, size) in pictures.items():
        scene = with_size(view, size)
        judge = preset.judge(loop, scene)
        out[index] = {"pixels_differ": differ(got, preset.reference(loop, scene))}
        out[index] |= {} if judge is None else judge(got)
    return out


def frames_of(args, preset):
    """The run on a Loop: the frames along the path with the resizes, the checked
    pictures against the preset's REFERENCE and JUDGE; the record."""
    scene, checked = preset.scene, set(args.check)
    resize = {at: (width, height) for width, height, at in args.resize}

    def frames(loop):
        cameras = path.path(args.path, scene["camera"], args.frames)
        done, resized, pictures, host = [], [], {}, []
        for index, camera in enumerate(cameras):
            if index in resize:
                began = time.perf_counter()
                reloaded = loop.resize(resize[index])
                ms = (time.perf_counter() - began) * 1e3
                resized.append(
                    {"frame": index, "size": list(loop.size), "reloaded": reloaded}
                    | {"host_ms": round(ms, 1)}
                )
            began = time.perf_counter()
            frame = loop.frame(sized_camera(camera, loop.size), index in checked)
            if args.pictures and index not in checked and frame.code == 0:
                loop.picture()
            host.append((time.perf_counter() - began) * 1e3)
            done.append(frame)
            if index in checked:
                pictures[index] = (frame.picture, dict(scene, camera=camera), loop.size)
            if frame.code:
                break
        loop.stop()
        results = {
            name: [report.result_at(loop, frame, name) for frame in done]
            for name in report.columns(loop)[1]
        }
        extra = {"path": args.path, "pictures_judged": judged(preset, loop, pictures)}
        extra |= {"far_field": preset.far_field}
        extra |= {"resized": resized, "pictures": args.pictures}
        extra |= {"host_ms": host_figures(host)}
        extra |= {"ms_sum_of_layers": layer_sums(loop, done), "results": results}
        return report.record(loop, done, extra)

    frames.__qualname__ = f"run_{args.pipeline}"
    return frames


def run(args):
    """The command `run`: 0, or 1 on a frame code that is not 0."""
    options = {"cores": args.cores, **dict(args.option)}
    try:
        preset = opened(args.pipeline, args.scene, args.view, args.size, options)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    args.frames = args.frames or int(preset.options.get("frames", 1))
    name = args.name or "_".join(
        [args.scene, *([args.view] if args.view else [])]
        + [*map(str, preset.size), args.path]
    )
    frames = frames_of(args, preset)
    with km.Session(card=args.card) as session:
        loop = preset.open(session)
        try:
            if args.out is None:
                record = frames(loop)
            else:
                record = harness.run(frames, loop, args.out / f"{name}.json")
        finally:
            loop.stop()
    print(json.dumps(record, default=float), flush=True)
    numbers = record.get("numbers", record)
    return 1 if numbers["codes_not_0"] else 0
