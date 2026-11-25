"""PNG files with numpy and zlib only: writing grey or RGB bytes, reading them back."""

import struct
import zlib
from pathlib import Path

import numpy as np


def chunk(tag, data):
    """One PNG chunk: length, tag, data, CRC."""
    body = tag + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))


def write_png(path, image):
    """Writes a uint8 array (H, W) as grey or (H, W, 3) as RGB."""
    image = np.ascontiguousarray(image, dtype=np.uint8)
    height, width = image.shape[:2]
    color_type = 0 if image.ndim == 2 else 2
    rows = image.reshape(height, -1)
    raw = b"".join(b"\x00" + rows[y].tobytes() for y in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
    data += chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")
    Path(path).write_bytes(data)


def read_png(path):
    """Reads a PNG written by `write_png` back into a uint8 array."""
    data = Path(path).read_bytes()
    pos, idat, shape = 8, b"", None
    while pos < len(data):
        (size,) = struct.unpack(">I", data[pos : pos + 4])
        tag, body = data[pos + 4 : pos + 8], data[pos + 8 : pos + 8 + size]
        if tag == b"IHDR":
            width, height, _, color_type = struct.unpack(">IIBB", body[:10])
            shape = (height, width) if color_type == 0 else (height, width, 3)
        elif tag == b"IDAT":
            idat += body
        pos += 12 + size
    rows = np.frombuffer(zlib.decompress(idat), dtype=np.uint8)
    return rows.reshape(shape[0], -1)[:, 1:].reshape(shape)
