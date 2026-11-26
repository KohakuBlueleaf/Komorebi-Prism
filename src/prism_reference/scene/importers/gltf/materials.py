"""glTF materials, textures, samplers and images (sizes from their headers, never decoded);
extensions read here and the others carried by name."""

import mmap
import struct

import numpy as np

from prism_reference.scene.description.types import (
    Image,
    Material,
    Note,
    Sampler,
    Texture,
    TextureUse,
)
from prism_reference.scene.importers.gltf.container import (
    data_uri,
    uri_path,
    view_bytes,
)

WRAPS = {10497: "REPEAT", 33071: "CLAMP", 33648: "MIRROR"}
FILTERS = {
    9728: "NEAREST",
    9729: "LINEAR",
    9984: "NEAREST_MIPMAP_NEAREST",
    9985: "LINEAR_MIPMAP_NEAREST",
    9986: "NEAREST_MIPMAP_LINEAR",
    9987: "LINEAR_MIPMAP_LINEAR",
}
READ_EXTENSIONS = ("KHR_materials_emissive_strength", "KHR_materials_unlit")
JPEG_SOF = set(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}


def _jpeg_size(data):
    """(mime, width, height) from a JPEG's first frame header, or None."""
    at = 2
    while at + 9 <= len(data):
        if data[at] != 0xFF:
            return None
        marker = data[at + 1]
        if marker == 0xFF:
            at += 1
            continue
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            at += 2
            continue
        (length,) = struct.unpack_from(">H", data, at + 2)
        if marker in JPEG_SOF:
            height, width = struct.unpack_from(">HH", data, at + 5)
            return "image/jpeg", width, height
        at += 2 + length
    return None


def _webp_size(data):
    """(mime, width, height) from a WebP's VP8, VP8L or VP8X chunk, or None."""
    chunk = bytes(data[12:16])
    if chunk == b"VP8 " and len(data) >= 30:
        width, height = struct.unpack_from("<HH", data, 26)
        return "image/webp", width & 0x3FFF, height & 0x3FFF
    if chunk == b"VP8L" and len(data) >= 25:
        (bits,) = struct.unpack_from("<I", data, 21)
        return "image/webp", (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if chunk == b"VP8X" and len(data) >= 30:
        w = int.from_bytes(data[24:27], "little") + 1
        h = int.from_bytes(data[27:30], "little") + 1
        return "image/webp", w, h
    return None


def image_header(data):
    """(mime, width, height) of PNG, JPEG or WebP bytes; ("", 0, 0) for anything else."""
    found = None
    if bytes(data[:8]) == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        width, height = struct.unpack_from(">II", data, 16)
        found = "image/png", width, height
    elif bytes(data[:2]) == b"\xff\xd8":
        found = _jpeg_size(data)
    elif bytes(data[:4]) == b"RIFF" and bytes(data[8:12]) == b"WEBP":
        found = _webp_size(data)
    return found or ("", 0, 0)


def _file_header(path):
    """image_header of a file beside the scene; ("", 0, 0) when it is missing."""
    if not path.is_file() or path.stat().st_size == 0:
        return "", 0, 0
    with (
        open(path, "rb") as handle,
        mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as mapped,
    ):
        view = memoryview(mapped)
        try:
            return image_header(view)
        finally:
            view.release()


def images(container):
    """The Image of every glTF image."""
    found = []
    for entry in container.doc.get("images", []):
        image = Image(name=entry.get("name", ""), mime=entry.get("mimeType", ""))
        uri = entry.get("uri")
        if "bufferView" in entry:
            image.data, _ = view_bytes(container, entry["bufferView"])
            header = image_header(image.data)
        elif uri is not None and uri.startswith("data:"):
            image.data = memoryview(data_uri(uri))
            header = image_header(image.data)
        elif uri is not None:
            path = uri_path(container.folder, uri)
            image.uri = str(path)
            header = _file_header(path)
        else:
            header = "", 0, 0
        image.mime = image.mime or header[0]
        image.width, image.height = header[1], header[2]
        found.append(image)
    return found


def samplers(doc):
    """The Sampler of every glTF sampler."""
    return [
        Sampler(
            WRAPS.get(s.get("wrapS", 10497), "REPEAT"),
            WRAPS.get(s.get("wrapT", 10497), "REPEAT"),
            FILTERS.get(s.get("magFilter")),
            FILTERS.get(s.get("minFilter")),
        )
        for s in doc.get("samplers", [])
    ]


def textures(doc):
    """The Texture of every glTF texture."""
    return [
        Texture(t.get("source", -1), t.get("sampler", -1))
        for t in doc.get("textures", [])
    ]


def texture_use(info, counts):
    """The TextureUse of a textureInfo (None when absent), its transform applied."""
    if info is None:
        return None
    use = TextureUse(info["index"], info.get("texCoord", 0))
    transform = info.get("extensions", {}).get("KHR_texture_transform")
    if transform is not None:
        counts["KHR_texture_transform"] = counts.get("KHR_texture_transform", 0) + 1
        use.offset = np.array(transform.get("offset", [0.0, 0.0]), np.float64)
        use.rotation = float(transform.get("rotation", 0.0))
        use.scale = np.array(transform.get("scale", [1.0, 1.0]), np.float64)
        use.uv = transform.get("texCoord", use.uv)
    return use


def material(entry, counts):
    """The Material of one glTF material; `counts` gathers extension names by use."""
    pbr = entry.get("pbrMetallicRoughness", {})
    out = Material(name=entry.get("name", ""))
    out.base_color = np.array(pbr.get("baseColorFactor", [1, 1, 1, 1]), np.float64)
    out.base_color_texture = texture_use(pbr.get("baseColorTexture"), counts)
    out.metallic = float(pbr.get("metallicFactor", 1.0))
    out.roughness = float(pbr.get("roughnessFactor", 1.0))
    out.metallic_roughness_texture = texture_use(
        pbr.get("metallicRoughnessTexture"), counts
    )
    normal = entry.get("normalTexture")
    out.normal_texture = texture_use(normal, counts)
    out.normal_scale = float((normal or {}).get("scale", 1.0))
    occlusion = entry.get("occlusionTexture")
    out.occlusion_texture = texture_use(occlusion, counts)
    out.occlusion_strength = float((occlusion or {}).get("strength", 1.0))
    out.emissive = np.array(entry.get("emissiveFactor", [0, 0, 0]), np.float64)
    out.emissive_texture = texture_use(entry.get("emissiveTexture"), counts)
    out.alpha_mode = entry.get("alphaMode", "OPAQUE")
    out.alpha_cutoff = float(entry.get("alphaCutoff", 0.5))
    out.double_sided = bool(entry.get("doubleSided", False))
    for name, value in entry.get("extensions", {}).items():
        counts[name] = counts.get(name, 0) + 1
        if name == "KHR_materials_emissive_strength":
            out.emissive_strength = float(value.get("emissiveStrength", 1.0))
        elif name == "KHR_materials_unlit":
            out.unlit = True
        else:
            out.carried[name] = value
    return out


def materials(container):
    """Materials, textures, samplers, images and the notes of what was read and carried."""
    doc = container.doc
    counts = {}
    found = [material(entry, counts) for entry in doc.get("materials", [])]
    notes = [
        Note("used", what, len(doc.get(key, [])))
        for what, key in (
            ("materials", "materials"),
            ("textures", "textures"),
            ("samplers", "samplers"),
            ("images", "images"),
        )
        if doc.get(key)
    ]
    for name, count in sorted(counts.items()):
        kind = "used" if name in READ_EXTENSIONS + ("KHR_texture_transform",) else None
        notes.append(Note(kind or "carried", name, count))
    return found, textures(doc), samplers(doc), images(container), notes
