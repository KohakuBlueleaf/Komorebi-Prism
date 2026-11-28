"""A public scene's textures: finding the images an MTL names, decoding them, their mip
chains."""

import io
import zipfile

import numpy as np

from prism_reference.scene.importers import meshio

try:
    from PIL import Image
except ImportError:
    Image = None

LEVELS_VERSION = 2  # of a mip chain: raised when decoding or the levels change
TEXTURE_SIDE = 1024
MIP_LEVELS = 11
HEIGHT_GAIN = 2.0  # slope scale when a bump map holds heights, not normals
NORMAL_LEAST_Z = 0.5**0.5  # a normal map's vector turned up to this z when below it


def decode_image(data):
    """The pixels of an image file's bytes as uint8 (H, W, C), C = 1 (grey), 2 (grey,
    alpha), 3 (RGB) or 4 (RGBA). Decoded by Pillow, needed here only."""
    if Image is None:
        raise RuntimeError(
            "the materials conversion decodes textures with Pillow, which is not "
            'installed; it is the "scenes" extra: pip install -e ".[scenes]"'
        )
    with Image.open(io.BytesIO(data)) as image:
        if image.mode in ("I;16", "I;16B", "I;16L", "I"):
            grey = np.asarray(image, dtype=np.float64)
            top = 65535.0 if grey.max() > 255 else 255.0
            return np.rint(grey * (255.0 / top)).astype(np.uint8)[:, :, None]
        mode = {"1": "L", "L": "L", "LA": "LA", "RGB": "RGB"}.get(image.mode, "RGBA")
        if image.mode == "P" and "transparency" not in image.info:
            mode = "RGB"
        pixels = np.asarray(image.convert(mode), dtype=np.uint8)
    return pixels.reshape(pixels.shape[0], pixels.shape[1], -1)


def halve(image):
    """A (H, W, 4) uint8 image box-filtered to half size (a side of 1 stays 1)."""
    height, width = image.shape[:2]
    rows, columns = (2 if height > 1 else 1), (2 if width > 1 else 1)
    h, w = height // rows, width // columns
    total = np.zeros((h, w, 4), dtype=np.uint16)
    for row in range(rows):
        for column in range(columns):
            total += image[row : h * rows : rows, column : w * columns : columns]
    n = rows * columns
    return ((total + n // 2) // n).astype(np.uint8)


def heights_to_normals(height):
    """A tangent-space normal map (RGBA8) from a height map (H, W) in [0, 1]."""
    du = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) / 2
    # Rows run down the image, v runs up.
    dv = -(np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) / 2
    n = np.stack([-HEIGHT_GAIN * du, -HEIGHT_GAIN * dv, np.ones_like(height)], -1)
    n /= np.sqrt((n * n).sum(axis=-1, keepdims=True))
    rgb = np.rint((n * 0.5 + 0.5) * 255).astype(np.uint8)
    return np.concatenate([rgb, np.full(height.shape + (1,), 255, np.uint8)], -1)


def unit_normals(image):
    """A normal map (H, W, 4) uint8 with each vector made unit and, where its z is under
    NORMAL_LEAST_Z, turned about its own azimuth up to it; a zero vector up."""
    vector = image[:, :, :3].astype(np.float64) * (2.0 / 255.0) - 1.0
    length = np.sqrt((vector * vector).sum(axis=-1, keepdims=True))
    up = np.zeros_like(vector)
    up[:, :, 2] = 1.0
    vector = np.where(length > 1e-6, vector / np.maximum(length, 1e-6), up)
    side = np.sqrt((vector[:, :, :2] ** 2).sum(axis=-1, keepdims=True))
    z = NORMAL_LEAST_Z
    scale = np.sqrt(1.0 - z * z) / np.maximum(side, 1e-6)
    turned = np.concatenate([vector[:, :, :2] * scale, np.full_like(side, z)], -1)
    turned = np.where(side > 1e-6, turned, up)
    vector = np.where(vector[:, :, 2:3] < z, turned, vector)
    rgb = np.rint((vector * 0.5 + 0.5) * 255).astype(np.uint8)
    return np.concatenate([rgb, image[:, :, 3:4]], axis=-1)


def texture_levels(pixels, role):
    """The mip chain (list of (h, w, 4) uint8, largest first) of decoded pixels in a
    role: "colour", "mask" or "normal"; larger than TEXTURE_SIDE is halved first; a
    normal map's vectors made unit and turned up first (unit_normals), its levels their
    averages."""
    channels = pixels.shape[2]
    grey = channels <= 2 or (
        (pixels[:, :, 0] == pixels[:, :, 1]).all()
        and (pixels[:, :, 1] == pixels[:, :, 2]).all()
    )
    if role == "mask":
        has_alpha = channels in (2, 4) and pixels[:, :, -1].min() < 255
        value = pixels[:, :, -1] if has_alpha else pixels[:, :, 0]
        image = np.repeat(value[:, :, None], 4, axis=2)
    elif channels <= 2:
        alpha = pixels[:, :, 1:2] if channels == 2 else None
        if alpha is None:
            alpha = np.full(pixels.shape[:2] + (1,), 255, np.uint8)
        image = np.concatenate([np.repeat(pixels[:, :, :1], 3, axis=2), alpha], 2)
    elif channels == 3:
        alpha = np.full(pixels.shape[:2] + (1,), 255, np.uint8)
        image = np.concatenate([pixels, alpha], axis=2)
    else:
        image = pixels
    if role == "normal" and not grey:
        image = unit_normals(image)
    while max(image.shape[:2]) > TEXTURE_SIDE:
        image = halve(image)
    if role == "normal" and grey:
        image = heights_to_normals(image[:, :, 0].astype(np.float64) / 255.0)
    levels = [np.ascontiguousarray(image)]
    while max(levels[-1].shape[:2]) > 1:
        levels.append(halve(levels[-1]))
    return levels


def decode_levels(job):
    """The mip chain of one texture: job = (archive path, member, role)."""
    archive, member, role = job
    return texture_levels(decode_image(meshio.read_member(archive, member)), role)


class TextureFiles:
    """Finds the image an MTL statement names: in a texture archive of the table when
    the path's first folder is one of them, else beside the OBJ; names without case."""

    def __init__(self, mesh_archive, obj_member, archives):
        self.obj_folder = (
            obj_member.rsplit("/", 1)[0] + "/" if "/" in obj_member else ""
        )
        self.mesh_archive = mesh_archive
        self.archives = {k.lower(): v for k, v in archives.items()}
        self.members = {}

    def names(self, archive):
        """{lower-case member name: member name} of an archive."""
        if archive not in self.members:
            with zipfile.ZipFile(archive) as z:
                self.members[archive] = {n.lower(): n for n in z.namelist()}
        return self.members[archive]

    def find(self, text):
        """(archive, member) of a map statement's file, or None when it is missing."""
        if not text:
            return None
        path = text.split()[-1] if text.startswith("-") else text
        parts = [
            p for p in path.replace("\\", "/").split("/") if p not in ("", ".", "..")
        ]
        if not parts:
            return None
        if parts[0].lower() in self.archives and len(parts) > 1:
            archive, member = self.archives[parts[0].lower()], "/".join(parts[1:])
        else:
            archive, member = self.mesh_archive, self.obj_folder + "/".join(parts)
        found = self.names(archive).get(member.lower())
        return (archive, found) if found else None
