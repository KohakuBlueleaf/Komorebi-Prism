"""The truths' index of `compare.py`'s cache: by kept truth, the scene's key, the .glb's
path and SHA-256, the size, the samples, the date and Blender's version; a kept truth
whose .glb hash differs from the scene's is refused."""

import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

INDEX = "index.json"
CHUNK_BYTES = 1 << 22


def glb_hash(glb):
    """The SHA-256 hex digest of the .glb's bytes (streamed)."""
    digest = hashlib.sha256()
    with open(glb, "rb") as f:
        while block := f.read(CHUNK_BYTES):
            digest.update(block)
    return digest.hexdigest()


def blender_version(executable):
    """The first line of `blender --version`, or None."""
    try:
        done = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    lines = done.stdout.strip().splitlines()
    return lines[0].strip() if lines else None


def index_of(cache):
    """The cache's index: {truth stem relative to the cache: entry}."""
    path = Path(cache) / INDEX
    return json.loads(path.read_text()) if path.exists() else {}


def noted(cache, stem, glb, key, record, executable):
    """Writes the kept truth's entry into the cache's index; the entry."""
    w, h = record["size"]
    entry = {"scene": Path(stem).parent.name, "key": key, "glb": str(glb)}
    entry |= {"glb_sha256": glb_hash(glb), "size": [w, h]}
    entry |= {"samples": record.get("samples"), "camera": record.get("camera")}
    entry |= {"date": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
    entry |= {"blender": blender_version(executable)}
    index = index_of(cache)
    index[str(Path(stem).relative_to(cache))] = entry
    path = Path(cache) / INDEX
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(index, indent=1))
    temporary.replace(path)
    return entry


def checked(cache, stem, glb):
    """The kept truth's index entry; SystemExit when it has none or its .glb hash is
    not the scene's .glb's."""
    entry = index_of(cache).get(str(Path(stem).relative_to(cache)))
    if entry is None:
        raise SystemExit(f"{stem}: kept truth not in {Path(cache) / INDEX}")
    found = glb_hash(glb)
    if entry["glb_sha256"] != found:
        raise SystemExit(
            f"{stem}: kept truth of {entry['glb']} (sha256 {entry['glb_sha256'][:12]})"
            f", the scene's {glb} is {found[:12]}"
        )
    return entry
