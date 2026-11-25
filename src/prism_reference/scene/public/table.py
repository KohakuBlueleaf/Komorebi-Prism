"""The table of public scenes (`public_scenes.json`), their views and their downloads."""

import hashlib
import json
import os
import shutil
import urllib.request
from pathlib import Path

TABLE = Path(__file__).resolve().parent / "public_scenes.json"
EXTRA_VARIABLE = "PRISM_SCENES_EXTRA"
CHUNK_BYTES = 1 << 20


def table():
    """{scene name: entry} of `public_scenes.json`, plus the entries of the JSON file
    named by $PRISM_SCENES_EXTRA (same layout) when it is set; not `environments`."""
    entries = json.loads(TABLE.read_text())
    extra = os.environ.get(EXTRA_VARIABLE)
    if extra:
        entries |= json.loads(Path(extra).read_text())
    entries.pop("environments", None)
    return entries


def views():
    """{view name `<scene>_<view>`: (scene name, view name)} of every view."""
    return {
        f"{name}_{view}": (name, view)
        for name, entry in table().items()
        for view in entry["views"]
    }


def is_view(name):
    """True when `name` is a view of a public scene."""
    return name in views()


def scene_of(name):
    """The scene of `name`: a view's scene, else `name` itself."""
    return views()[name][0] if is_view(name) else name


def triangles(view):
    """The triangle count recorded in the table for a view's scene (0 if unknown)."""
    name, _ = views()[view]
    return int(table()[name].get("triangles", 0))


def public_dir(data):
    """Where downloads and converted meshes go: <data>/public."""
    path = Path(data) / "public"
    (path / "downloads").mkdir(parents=True, exist_ok=True)
    return path


def sha256(path):
    """SHA-256 hex digest of a file."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(CHUNK_BYTES):
            digest.update(block)
    return digest.hexdigest()


def download(url, path, expected):
    """Downloads url to path unless a file with the expected SHA-256 is there."""
    if path.exists() and sha256(path) == expected:
        return path
    part = path.with_name(path.name + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "scene-fetch"})
    with urllib.request.urlopen(request, timeout=60) as r, open(part, "wb") as f:
        shutil.copyfileobj(r, f, CHUNK_BYTES)
    got = sha256(part)
    if got != expected:
        raise ValueError(f"{url}: SHA-256 {got}, expected {expected}")
    part.replace(path)
    return path


def fetch(name, data, key="files"):
    """Downloads the files of a scene (checked) and returns their local paths; key
    "texture_files" gives its texture archives, kept in downloads/textures/."""
    folder = public_dir(data) / "downloads"
    if key == "texture_files":
        folder = folder / "textures"
        folder.mkdir(exist_ok=True)
    return [
        download(
            f["url"], folder / f.get("file", f["url"].rsplit("/", 1)[1]), f["sha256"]
        )
        for f in table()[name].get(key, [])
    ]
