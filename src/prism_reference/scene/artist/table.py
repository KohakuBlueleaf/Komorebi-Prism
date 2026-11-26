"""The table of artists' scenes (`artist_scenes.json`), their downloads and their files."""

import json
import shutil
import urllib.request
import zipfile
from pathlib import Path

from prism_reference.scene.public.table import CHUNK_BYTES, sha256

TABLE = Path(__file__).resolve().parent / "artist_scenes.json"
TIMEOUT_SECONDS = 60


def table():
    """{scene key: row} of `artist_scenes.json`."""
    return json.loads(TABLE.read_text())


def attribution(key):
    """A row's attribution line: name, author, licence and where it was read."""
    row = table()[key]
    return (
        f"{row['name']} by {row['author']}, {row['licence']} "
        f"({row['licence_from']}), {row['url']}"
    )


def artist_dir(data):
    """Where downloads and exports go: <data>/artist."""
    path = Path(data) / "artist"
    (path / "downloads").mkdir(parents=True, exist_ok=True)
    return path


def download_path(key, data):
    """The local path of a row's downloaded file."""
    return artist_dir(data) / "downloads" / table()[key]["url"].rsplit("/", 1)[1]


def is_present(key, data):
    """True when the row's file is there with its bytes and SHA-256."""
    row, path = table()[key], download_path(key, data)
    return (
        path.exists()
        and path.stat().st_size == row["bytes"]
        and sha256(path) == row["sha256"]
    )


def download(key, data):
    """Downloads a row's file with a plain client and checks it; False when kept."""
    if is_present(key, data):
        return False
    row, path = table()[key], download_path(key, data)
    part = path.with_name(path.name + ".part")
    with (
        urllib.request.urlopen(row["url"], timeout=TIMEOUT_SECONDS) as r,
        open(part, "wb") as f,
    ):
        shutil.copyfileobj(r, f, CHUNK_BYTES)
    got = sha256(part)
    if got != row["sha256"]:
        raise ValueError(f"{row['url']}: SHA-256 {got}, expected {row['sha256']}")
    part.replace(path)
    return True


def unpack(key, data):
    """Unpacks a row's archive beside it, once; returns the folder or None."""
    path = download_path(key, data)
    if not table()[key]["member"]:
        return None
    folder = path.with_suffix("")
    if not folder.exists():
        part = folder.with_name(folder.name + ".part")
        with zipfile.ZipFile(path) as archive:
            archive.extractall(part)
        part.replace(folder)
    return folder


def blend_path(key, data):
    """The local `.blend` of a row: the plain file, or its member in the unpacked
    archive."""
    row = table()[key]
    path = download_path(key, data)
    return path.with_suffix("") / row["member"] if row["member"] else path
