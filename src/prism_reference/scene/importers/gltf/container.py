"""A glTF file's JSON and buffers: `.glb` chunks or `.gltf` with external buffers and data
URIs; files are memory-mapped and every buffer is a read-only memoryview."""

import base64
import json
import mmap
import struct
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

GLB_MAGIC = 0x46546C67
CHUNK_JSON = 0x4E4F534A
CHUNK_BIN = 0x004E4942


@dataclass
class Container:
    """The parsed JSON, one memoryview per buffer and the folder relative URIs start in."""

    doc: dict
    buffers: list
    folder: Path
    format: str
    bytes: int
    maps: list = field(default_factory=list)


def _map(path):
    """A read-only memory map of a whole file (an empty view for an empty file)."""
    with open(path, "rb") as handle:
        if Path(path).stat().st_size == 0:
            return None, memoryview(b"")
        mapped = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
    return mapped, memoryview(mapped)


def data_uri(uri):
    """The bytes of a base64 `data:` URI."""
    head, _, payload = uri.partition(",")
    if not head.endswith(";base64"):
        raise ValueError(f"data URI without base64: {head[:40]}")
    return base64.b64decode(payload)


def uri_path(folder, uri):
    """The path a relative URI names beside the file."""
    return folder / unquote(uri)


def _glb(view):
    """The JSON and the BIN chunk (or None) of a `.glb` held in `view`."""
    magic, version, length = struct.unpack_from("<III", view, 0)
    if magic != GLB_MAGIC:
        raise ValueError("not a glb file: bad magic")
    if version != 2:
        raise ValueError(f"glb version {version}: not supported")
    at, doc, binary = 12, None, None
    while at + 8 <= min(length, len(view)):
        size, kind = struct.unpack_from("<II", view, at)
        chunk = view[at + 8 : at + 8 + size]
        if kind == CHUNK_JSON and doc is None:
            doc = json.loads(bytes(chunk))
        elif kind == CHUNK_BIN and binary is None:
            binary = chunk
        at += 8 + ((size + 3) & ~3)
    if doc is None:
        raise ValueError("glb without a JSON chunk")
    return doc, binary


def open_container(path):
    """The Container of a `.glb` or `.gltf` file."""
    path = Path(path)
    folder = path.parent
    maps = []
    mapped, view = _map(path)
    maps.append(mapped)
    if view[:4] == b"glTF":
        doc, binary = _glb(view)
        kind = "glb"
    else:
        doc, binary = json.loads(bytes(view)), None
        kind = "gltf"
    buffers = []
    for i, entry in enumerate(doc.get("buffers", [])):
        uri = entry.get("uri")
        if uri is None:
            if binary is None:
                raise ValueError(f"buffer {i}: no uri and no BIN chunk")
            buffers.append(binary)
        elif uri.startswith("data:"):
            buffers.append(memoryview(data_uri(uri)))
        else:
            mapped, view = _map(uri_path(folder, uri))
            maps.append(mapped)
            buffers.append(view)
        if len(buffers[-1]) < entry.get("byteLength", 0):
            raise ValueError(
                f"buffer {i}: {len(buffers[-1])} bytes, byteLength {entry['byteLength']}"
            )
    return Container(doc, buffers, folder, kind, path.stat().st_size, maps)


def view_bytes(container, index):
    """The bytes of buffer view `index` and its byteStride (None when absent)."""
    entry = container.doc["bufferViews"][index]
    start = entry.get("byteOffset", 0)
    data = container.buffers[entry["buffer"]][start : start + entry["byteLength"]]
    return data, entry.get("byteStride")
