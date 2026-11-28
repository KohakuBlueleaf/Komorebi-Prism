"""A scene file opened once: converted under a name from the digest of its files, kept
under the data root with its entry in `opened_scenes.json`, found again unchanged."""

import hashlib
import json
import math
import os
import time
from pathlib import Path

from prism_reference.scene.artist.convert import convert
from prism_reference.scene.importers.gltf.sidecar import sidecar_path
from prism_reference.scene.public.materials import made_now
from prism_reference.scene.public.table import OPENED_TABLE, public_dir

CONVERTER = 7  # raised when the conversion's output changes
DIGEST_HEX = 10  # hex digits of the key in a name
CHUNK_BYTES = 1 << 22
GENERIC_STEM = "scene"


def scene_files(path):
    """The files a scene's conversion reads: the scene file, then its sidecar and the
    sidecar's instance table when they are there."""
    path = Path(path)
    files = [path]
    sidecar = sidecar_path(path)
    if sidecar.is_file():
        files.append(sidecar)
        table = json.loads(sidecar.read_text()).get("instances")
        if table is not None and (path.parent / table["file"]).is_file():
            files.append(path.parent / table["file"])
    return files


def file_key(path, camera=None):
    """The BLAKE2b hex digest (streamed) of the scene's files, CONVERTER and the
    arguments that change the conversion's output."""
    digest = hashlib.blake2b()
    for file in scene_files(path):
        digest.update(f"{file.name}\0{file.stat().st_size}\0".encode())
        with open(file, "rb") as f:
            while block := f.read(CHUNK_BYTES):
                digest.update(block)
    digest.update(json.dumps({"converter": CONVERTER, "camera": camera}).encode())
    return digest.hexdigest()


def file_stats(path):
    """Per file the conversion reads: its resolved path, size, modification and change
    times (ns), device and inode."""
    out = []
    for file in scene_files(path):
        info = file.stat()
        out.append(
            [str(file.resolve()), info.st_size, info.st_mtime_ns, info.st_ctime_ns]
            + [info.st_dev, info.st_ino]
        )
    return out


def found_by_stats(stats, camera, data):
    """(name, key) of the table's entry converted from files of these `stats` with
    `camera` by this CONVERTER; None when there is none."""
    for name, entry in opened_table(data).items():
        opened = entry.get("opened", {})
        if (
            opened.get("files") == stats
            and opened.get("camera") == camera
            and opened.get("converter") == CONVERTER
        ):
            return name, opened["key"]
    return None


def scene_name(path, key):
    """`<stem>_<first DIGEST_HEX hex digits>`: the file's stem, its folder's when the
    stem is GENERIC_STEM."""
    path = Path(path).resolve()
    stem = path.stem if path.stem != GENERIC_STEM else path.parent.name
    return f"{stem}_{key[:DIGEST_HEX]}"


def opened_table(data):
    """{name: entry} of `<data>/opened_scenes.json`; empty when missing."""
    path = Path(data) / OPENED_TABLE
    return json.loads(path.read_text()) if path.exists() else {}


def kept(name, key, data):
    """True when the table holds `name` with `key` and its mesh and materials exist,
    the materials made at today's versions."""
    entry = opened_table(data).get(name)
    folder = public_dir(data)
    materials = folder / f"{name}_materials.npz"
    return (
        entry is not None
        and entry.get("opened", {}).get("key") == key
        and (folder / f"{name}.npz").is_file()
        and materials.is_file()
        and made_now(materials)
    )


def keep(name, entry, data):
    """`entry` written under `name` in the table (its other entries kept; written to a
    temporary name, then renamed)."""
    path = Path(data) / OPENED_TABLE
    entries = opened_table(data) | {name: entry}
    part = path.with_name(f"{path.name}.{os.getpid()}.part")
    part.write_text(json.dumps(entries, indent=1) + "\n")
    part.replace(path)


def stamped(name, key, stats, camera, data):
    """The table's entry `name` given the files' `stats` and `camera` it was opened
    with (written only when they differ)."""
    entry = opened_table(data)[name]
    opened = entry.setdefault("opened", {})
    if opened.get("files") == stats and opened.get("camera") == camera:
        return
    opened |= {"key": key, "files": stats, "camera": camera}
    keep(name, entry, data)


def open_scene(path, data, camera=None, most_triangles=None, workers=4):
    """The scene name of a glTF file and the record of its open: found by its files'
    stats when an entry was opened from them, else by their digest; converted into the
    data root when its key is not kept there (`most_triangles` None: no count refused).
    The record holds the key, `converted`, how it was found (`stats` or `digest`), the
    seconds of finding it and the conversion's report."""
    started = time.perf_counter()
    stats = file_stats(path)
    found = found_by_stats(stats, camera, data)
    if found is not None and kept(*found, data):
        name, key = found
        record = {"name": name, "key": key, "found": "stats"}
        record["digest_seconds"] = round(time.perf_counter() - started, 3)
        return name, record | {"converted": False}
    key = file_key(path, camera)
    name = scene_name(path, key)
    record = {"name": name, "key": key, "found": "digest"}
    record["digest_seconds"] = round(time.perf_counter() - started, 3)
    if kept(name, key, data):
        stamped(name, key, stats, camera, data)
        return name, record | {"converted": False}
    started = time.perf_counter()
    most = math.inf if most_triangles is None else most_triangles
    entry, report = convert(path, name, data, camera, most, workers=workers)
    report["seconds"] = round(time.perf_counter() - started, 3)
    entry["opened"] = {"key": key, "converter": CONVERTER, "file": Path(path).name}
    entry["opened"] |= {"files": stats, "camera": camera}
    keep(name, entry, data)
    return name, record | {"converted": True, "report": report}
