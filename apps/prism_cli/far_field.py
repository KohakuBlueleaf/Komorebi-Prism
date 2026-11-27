"""A scene's far field built beside its frames: the sky's visibility bake when its lights
are not baked, its lights, then the block-by-block transport, in a child process of
the lowest priority, under a lock file (one build a scene), into a folder of its own
whose files are renamed into the data root when all are written; its record."""

import argparse
import fcntl
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from prism_common.paths import DATA_VARIABLE
from prism_reference.direct.prepare import prepare
from prism_reference.indirect.blockwise.build import build as build_blockwise
from prism_reference.scene.public import files
from prism_reference.scene.public.table import public_dir, table

FOLDER = ".far_field"  # under <data>/public: each scene's lock, record and work folder
METHOD = "sketch"  # the transport's build, block by block
KINDS = ("indirect", "transport")  # the far field's files, the last renamed last
SHARED = ("mesh", "materials")  # the scene's files the build reads, linked
MOST_WORKERS = 32
CHILDREN = {}  # by scene: the build this process started
IDLE = ("nice", "-n", "19", "chrt", "--idle", "0")  # the child's scheduling: idle


def work_root(data):
    """<data>/public/.far_field, made if missing."""
    path = public_dir(data) / FOLDER
    path.mkdir(parents=True, exist_ok=True)
    return path


def record_path(name, data):
    """The record of the scene's last build."""
    return work_root(data) / f"{name}.json"


def present(name, data):
    """True when the scene's far-field files are there."""
    return all(files.present(name, kind, data) for kind in KINDS)


def opened_scene(name):
    """True when `name` is a scene opened from a file (its entry has `opened`)."""
    return "opened" in table().get(name, {})


def locked(name, data, wait=False):
    """An open file holding the scene's build lock (released when closed); None when
    another process holds it and not `wait`."""
    handle = open(work_root(data) / f"{name}.lock", "a")  # noqa: SIM115
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
    except BlockingIOError:
        handle.close()
        return None
    return handle


def start(name, data):
    """The build of an opened scene's far field started when it lacks it and none runs:
    {"state": "present" | "building" | "started", "pid", "log"}; None for another
    scene."""
    if not opened_scene(name):
        return None
    if present(name, data):
        return {"state": "present"}
    held = locked(name, data)
    if held is None:
        return {"state": "building"}
    held.close()
    log = work_root(data) / f"{name}.log"
    command = [*IDLE, sys.executable, "-m", "prism_cli.far_field", name]
    command += ["--data", str(data)]
    environment = os.environ | {DATA_VARIABLE: str(data)}
    with open(log, "ab") as out:
        process = subprocess.Popen(
            command,
            stdout=out,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env=environment,
        )
    CHILDREN[name] = process
    return {"state": "started", "pid": process.pid, "log": log.name}


def running(name, data):
    """True while the scene's build runs: the child this process started, else any
    process holding its lock."""
    process = CHILDREN.get(name)
    if process is not None:
        return process.poll() is None
    held = locked(name, data)
    if held is None:
        return True
    held.close()
    return False


def last_record(name, data):
    """The record of the scene's last build; None without one."""
    path = record_path(name, data)
    return json.loads(path.read_text()) if path.is_file() else None


def wait(name, data):
    """Waits for the scene's build to end; its record (None without one) and whether
    the far field is there."""
    began = time.perf_counter()
    locked(name, data, wait=True).close()
    record = last_record(name, data)
    return record, present(name, data), round(time.perf_counter() - began, 3)


def baked(name, data):
    """True when the scene's lighting file holds a baked visibility."""
    counts = files.counts(name, "lighting", data)
    return counts is not None and counts.get("visibility", "baked") == "baked"


def linked(name, data, work):
    """A data root `work` whose public folder links the scene's mesh, materials and
    downloads (and its lighting and visibility when baked)."""
    shutil.rmtree(work, ignore_errors=True)
    folder = public_dir(work)
    kinds = SHARED + (("lighting",) if baked(name, data) else ())
    for kind in kinds:
        source = files.scene_file(name, kind, data)
        os.symlink(source, files.scene_file(name, kind, work))
    visibility = public_dir(data) / f"{name}_visibility.npz"
    if visibility.is_file():
        os.symlink(visibility, folder / visibility.name)
    os.rmdir(folder / "downloads")
    os.symlink(public_dir(data) / "downloads", folder / "downloads")
    return work


def placed(name, data, work):
    """The files the build wrote under `work` renamed into the data root: the
    visibility and lighting when made, the transport folder, the indirect file last."""
    source, target = public_dir(work), public_dir(data)
    moved = []
    names = [f"{name}_visibility.npz", files.FILES["lighting"][0].format(name=name)]
    for one in names:
        path = source / one
        if path.is_file() and not path.is_symlink():
            path.replace(target / one)
            moved.append(one)
    transport = files.scene_file(name, "transport", data)
    shutil.rmtree(transport, ignore_errors=True)
    files.scene_file(name, "transport", work).replace(transport)
    moved.append(transport.name)
    files.scene_file(name, "indirect", work).replace(
        files.scene_file(name, "indirect", data)
    )
    moved.append(files.scene_file(name, "indirect", data).name)
    return moved


def kept(path, record):
    """`record` written to `path` as JSON: a temporary name, then renamed."""
    part = path.with_name(f"{path.name}.{os.getpid()}.part")
    part.write_text(json.dumps(record, default=float) + "\n")
    part.replace(path)


def build(name, data, workers):
    """The scene's far field built in its work folder and renamed into place under
    the lock; its record (what was built, seconds by step)."""
    held = locked(name, data)
    if held is None:
        return {"name": name, "state": "building elsewhere"}
    with held:
        if present(name, data):
            return {"name": name, "state": "present"}
        record_path(name, data).unlink(missing_ok=True)
        began = time.perf_counter()
        work = linked(name, data, work_root(data) / name)
        record = {"name": name, "state": "built", "seconds": {}}
        if not baked(name, data):
            at = time.perf_counter()
            _, counts = prepare(name, work, workers, visibility="bake", shadow="card")
            record["seconds"]["lights"] = round(time.perf_counter() - at, 3)
            record["lights"] = {"visibility": counts.get("visibility"), "made": True}
        at = time.perf_counter()
        counts = build_blockwise(name, work, method=METHOD)
        record["seconds"]["transport"] = round(time.perf_counter() - at, 3)
        record["transport"] = {"method": METHOD, "steps": counts.get("seconds")}
        record["placed"] = placed(name, data, work)
        shutil.rmtree(work, ignore_errors=True)
        record["seconds"]["all"] = round(time.perf_counter() - began, 3)
        kept(record_path(name, data), record)
        return record


def built(name, data, workers):
    """`build`, a failure kept as the record (state `failed`, the error) and raised."""
    try:
        return build(name, data, workers)
    except Exception as error:
        record = {"name": name, "state": "failed", "error": f"{error!r}"}
        kept(record_path(name, data), record)
        raise


def main():
    """Builds a scene's far field (the child `start` runs)."""
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("name")
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument(
        "--workers",
        type=int,
        default=min(len(os.sched_getaffinity(0)), MOST_WORKERS),
    )
    args = parser.parse_args()
    print(json.dumps(built(args.name, args.data, args.workers), default=float))


if __name__ == "__main__":
    main()
