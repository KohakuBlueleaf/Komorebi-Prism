"""The table's lighting side: its environment maps and where a scene's lights are kept."""

import json

from prism_reference.scene.public.table import TABLE, download, public_dir


def environments():
    """{map name: entry} of the table's `environments` (the lighting's HDR maps)."""
    return json.loads(TABLE.read_text())["environments"]


def fetch_environment(name, data):
    """Downloads an environment map of the table (checked) into downloads/ and
    returns its local path in a list."""
    folder = public_dir(data) / "downloads"
    return [
        download(f["url"], folder / f["url"].rsplit("/", 1)[1], f["sha256"])
        for f in environments()[name]["files"]
    ]


def lighting_path(name, data):
    """<public>/<scene>_lighting.npz."""
    return public_dir(data) / f"{name}_lighting.npz"
