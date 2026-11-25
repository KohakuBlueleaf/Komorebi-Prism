"""A picture to JPEG bytes: an image (H, W, 3 or 4), or planes (P, H, W) laid out as the
slot frame.visibility's (depth, red, green, blue, ...); cut to the frame's size. `held`
is what the render loop hands to the encoders, `jpeg` what an encoder makes of it."""

import io

import numpy as np
from PIL import Image

QUALITY = 85
COLOUR_PLANES = slice(1, 4)  # red, green, blue of a planes picture


def colour(picture, size):
    """The picture's colour as uint8 (H, W, 3) of the frame's `size` (W, H), from the
    top-left of a padded picture; floats taken as 0 to 1."""
    picture = np.asarray(picture)
    if picture.ndim != 3:
        raise ValueError(f"a picture is 3-dimensional, not of shape {picture.shape}")
    if picture.shape[-1] in (3, 4):
        image = picture[..., :3]
    elif picture.shape[0] >= 4:
        image = np.moveaxis(picture[COLOUR_PLANES], 0, 2)
    else:
        raise ValueError(f"a picture of shape {picture.shape} has no colour")
    width, height = size
    image = image[:height, :width]
    if image.dtype != np.uint8:
        image = np.rint(np.clip(image, 0.0, 1.0) * 255.0).astype(np.uint8)
    return np.ascontiguousarray(image)


def held(picture, size):
    """The picture's colour of the frame's `size` (W, H) in memory of its own: an image
    uint8 (H, W, 4) copied as it is, any other picture through `colour`."""
    picture = np.asarray(picture)
    width, height = size
    if picture.ndim == 3 and picture.shape[-1] == 4 and picture.dtype == np.uint8:
        return np.array(picture[:height, :width], order="C", copy=True)
    image = colour(picture, size)
    return image.copy() if np.may_share_memory(image, picture) else image


def jpeg(image, out=None):
    """An image uint8 (H, W, 3 or 4: the fourth byte not read) as JPEG bytes; with `out`,
    a binary file of the caller's own, written there and read from it."""
    height, width, channels = image.shape
    if channels == 4:
        image = np.ascontiguousarray(image)
        frame = Image.frombuffer("RGB", (width, height), image, "raw", "RGBX", 0, 1)
    else:
        frame = Image.fromarray(image)
    if out is None:
        buffer = io.BytesIO()
        frame.save(buffer, "JPEG", quality=QUALITY)
        return buffer.getvalue()
    out.seek(0)
    out.truncate()
    frame.save(out, "JPEG", quality=QUALITY)
    out.seek(0)
    return out.read()


def decoded(data):
    """JPEG bytes as uint8 (H, W, 3)."""
    return np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))
