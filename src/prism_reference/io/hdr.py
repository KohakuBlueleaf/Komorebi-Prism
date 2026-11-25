"""Reading Radiance .hdr environment maps."""

from pathlib import Path

import numpy as np


def read_hdr(path):
    """The radiance (H, W, 3) float32 of a Radiance .hdr file (RGBE, flat or with the
    run-length rows of the format), rows from the top."""
    data = Path(path).read_bytes()
    end = data.index(b"\n\n") + 2
    line_end = data.index(b"\n", end)
    words = data[end:line_end].split()
    if words[0] != b"-Y" or words[2] != b"+X":
        raise ValueError(f"{path}: orientation {words} is not -Y H +X W")
    height, width = int(words[1]), int(words[3])
    raw, pos = np.frombuffer(data, dtype=np.uint8), line_end + 1
    rgbe = np.empty((height, width, 4), dtype=np.uint8)
    for y in range(height):
        head = raw[pos : pos + 4]
        if not (
            head[0] == 2
            and head[1] == 2
            and (int(head[2]) << 8 | int(head[3])) == width
        ):
            rgbe[y:] = raw[pos : pos + (height - y) * width * 4].reshape(-1, width, 4)
            break
        pos += 4
        for c in range(4):
            x = 0
            while x < width:
                count = int(raw[pos])
                if count > 128:
                    rgbe[y, x : x + count - 128, c] = raw[pos + 1]
                    x, pos = x + count - 128, pos + 2
                else:
                    rgbe[y, x : x + count, c] = raw[pos + 1 : pos + 1 + count]
                    x, pos = x + count, pos + 1 + count
    exponent = rgbe[:, :, 3].astype(np.int32)
    scale = np.where(exponent > 0, np.ldexp(1.0, exponent - 136), 0.0)
    return (rgbe[:, :, :3] * scale[:, :, None]).astype(np.float32)
