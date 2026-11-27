"""`open`: a scene file converted once (or found), its lights made in two steps (1 a
vertex for the sky's visibility first, the bake after), a preset's frames on its view,
the last picture as a PNG and one JSON record with the account of the load."""

import json
import os
import subprocess
import sys
import time
from contextlib import ExitStack

import komorebi as km
import numpy as np
from komorebi.device import native

from prism_cli import far_field
from prism_cli import preset as preset_module
from prism_cli.account import Account
from prism_cli.preset import ROOT, globals_of, opened
from prism_common.paths import data_root
from prism_reference.direct.prepare import prepare
from prism_reference.io.png import write_png
from prism_reference.scene.artist.entry import VIEW
from prism_reference.scene.artist.opened import open_scene
from prism_reference.scene.camera import sized_camera
from prism_reference.scene.public.lighting import lighting_path
from prism_reference.scene.public.table import public_dir

LIGHTING = ROOT / "scripts" / "data" / "public_scenes.py"
MOST_WORKERS = 32
READ_BACK = {"make_view": "read.mesh", "load_materials": "read.materials"}
READ_LIGHTS = "read.lights"


def lights_state(name, data):
    """`none` without a lighting file, else its visibility: `open` or `baked`."""
    path = lighting_path(name, data)
    if not path.exists():
        return "none"
    with np.load(path) as f:
        return json.loads(str(f["counts"])).get("visibility", "baked")


def bake_in_background(name, data):
    """The bake started as a detached process of its own, its log beside the scene's
    files: its PID and its log's name."""
    log = public_dir(data) / f"{name}_bake.log"
    command = [sys.executable, str(LIGHTING), "lighting", name]
    command += ["--visibility", "bake", "--shadow", "card", "--data", str(data)]
    with open(log, "ab") as out:
        process = subprocess.Popen(
            command,
            stdout=out,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    return {"pid": process.pid, "log": log.name}


def lights(args, name, data, account):
    """The lights a preset needs when there is no lighting file: `open` first, the bake
    by --bake, the shadow map left to the card; what was done."""
    done = {"made": None}
    if lights_state(name, data) != "none":
        return done
    if args.bake == "wait":
        workers = min(len(os.sched_getaffinity(0)), MOST_WORKERS)
        with account.part("lights.bake"):
            _, counts = prepare(name, data, workers, visibility="bake", shadow="card")
        return done | {"made": "bake", "counts": counts}
    with account.part("lights.open"):
        _, counts = prepare(name, data, visibility="open", shadow="card")
    account.add("lights.open", -counts["shadow_seconds"])
    account.add("lights.open.shadow_map", counts["shadow_seconds"])
    done |= {"made": "open", "counts": counts}
    if args.bake == "background":
        done["bake"] = bake_in_background(name, data)
    return done


def read_back(account):
    """The preset's reads of the scene's files timed: mesh, materials, lights."""
    for function, part in READ_BACK.items():
        account.patch(preset_module, function, account.timed(part))
    account.patch(preset_module, "load_lights", account.timed(READ_LIGHTS))


def frames(args, preset, loop, account, stem):
    """--frames frames on the view's camera, the first and the last with their
    pictures; the last written as a PNG; the frames' codes and the picture's path."""
    camera = sized_camera(preset.scene["camera"], loop.size)
    codes, picture = [], None
    began = time.perf_counter()
    for index in range(args.frames):
        asked = index in (0, args.frames - 1)
        frame = loop.frame(camera, asked)
        codes.append(frame.code)
        if index == 0:
            account.add("frame.first", time.perf_counter() - began)
            account.first_picture = account.since_start(), account.since_process()
        picture = frame.picture if frame.picture is not None else picture
        if frame.code:
            break
    account.add("frames", time.perf_counter() - began)
    path = None
    if picture is not None:
        args.out.mkdir(parents=True, exist_ok=True)
        path = args.out / f"{stem}_{args.pipeline}.png"
        write_png(path, picture[..., :3])
    return codes, path


def with_far_field(args, preset, name, data):
    """When the open started or found the far field's build: waits for it, then the
    preset opened again on a new session with the far field and its frames (the last
    picture `<name>_camera_far_field_<pipeline>.png`); what was waited and drawn."""
    if preset.building is None or preset.building["state"] == "present":
        return None
    record, there, seconds = far_field.wait(name, data)
    out = {"build": record, "present": there, "seconds": seconds}
    if not there:
        return out
    began = time.perf_counter()
    again = opened(args.pipeline, name, VIEW, args.size, {"frames": args.frames})
    with km.Session(card=args.card) as session:
        loop = again.open(session)
        try:
            stem = f"{name}_{VIEW}_far_field"
            codes, picture = frames(args, again, loop, Account(), stem)
        finally:
            loop.stop()
    out |= {"far_field": again.far_field, "codes": codes}
    out["picture"] = None if picture is None else picture.name
    return out | {"reload_seconds": round(time.perf_counter() - began, 3)}


def open_command(args):
    """The command `open`: 0, 1 on a frame code that is not 0, 2 when the card refused
    the load (its text in the record)."""
    account, data = Account(), data_root()
    workers = min(len(os.sched_getaffinity(0)), MOST_WORKERS)
    name, scene = open_scene(args.file, data, args.camera, args.most_triangles, workers)
    if scene["converted"]:
        account.convert_peak = account.peak_mib()
    account.add("digest", scene.pop("digest_seconds"))
    report = scene.pop("report", None)
    for step, seconds in (report or {}).get("steps", {}).items():
        account.add(f"convert.{step}", seconds)
    wanted = globals_of(args.pipeline).get("SCENE_INPUTS", ())
    made = lights(args, name, data, account) if "lights" in wanted else {"made": None}
    with account.part("module"):
        native.load_module()
    read_back(account)
    options = {"frames": args.frames}
    try:
        preset = opened(args.pipeline, name, VIEW, args.size, options, build=True)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    finally:
        account.restore()
    codes, picture, refused, waited = [], None, None, None
    with ExitStack() as stack:
        with account.part("session.start"):
            session = stack.enter_context(km.Session(card=args.card))
        account.hosts(preset.pipeline)
        account.session(session)
        account.loop()
        try:
            loop = preset.open(session)
        except (ValueError, km.KomorebiError) as error:
            refused = f"{type(error).__name__}: {error}"
        finally:
            account.restore()
        if refused is None:
            try:
                codes, picture = frames(args, preset, loop, account, f"{name}_{VIEW}")
            finally:
                loop.stop()
    if refused is None and args.wait_far_field:
        waited = with_far_field(args, preset, name, data)
    record = {"name": name, "file": args.file.name, "pipeline": args.pipeline}
    record |= {"converted": scene["converted"], "key": scene["key"]}
    record |= {"size": list(preset.size), "frames": len(codes), "codes": codes}
    record |= {"refused": refused, "lights": lights_state(name, data)}
    record |= {"far_field": preset.far_field, "far_field_build": preset.building}
    record |= {"far_field_wait": waited}
    record |= {"lights_made": made}
    record |= {"picture": None if picture is None else picture.name}
    if report is not None:
        record |= {"triangles": report["triangles"], "vertices": report["vertices"]}
    print(json.dumps(record | accounted(account), default=float), flush=True)
    return 2 if refused else 1 if any(codes) else 0


def accounted(account):
    """The record's times: to the first picture (from the command's start and from the
    process's), the command's seconds, the account with `other` (the rest)."""
    first = account.first_picture or (None, None)
    out = {"first_picture_seconds": first[0]}
    out["first_picture_seconds_from_process"] = first[1]
    out["seconds"] = account.since_start()
    out["account"] = account.record()
    parts = out["account"]["seconds"]
    timed = sum(v for k, v in parts.items() if k != "frame.first")
    timed += sum(row["seconds"] for row in out["account"]["tensors"].values())
    parts["other"] = round(out["seconds"] - timed, 3)
    return out
