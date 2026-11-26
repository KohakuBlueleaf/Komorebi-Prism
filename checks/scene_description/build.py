"""Writes the check's glTF files: a quad scene holding every attribute, accessor kind,
node kind, light, camera and material field, as `.glb` and as `.gltf`."""

import base64
import copy
import json
import struct
import zlib

import numpy as np

DTYPES = {5120: "i1", 5121: "u1", 5122: "<i2", 5123: "<u2", 5125: "<u4", 5126: "<f4"}
SIZES = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 2, "MAT3": 3, "MAT4": 4}


def png_bytes(width, height):
    """A PNG signature and IHDR chunk of the given size."""
    body = b"IHDR" + struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    crc = struct.pack(">I", zlib.crc32(body))
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + body + crc


def jpeg_bytes(width, height):
    """A JPEG start, an APP0 segment and a baseline frame header of the given size."""
    app0 = (
        b"\xff\xe0"
        + struct.pack(">H", 16)
        + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    )
    sof = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, height, width, 1) + b"\x01\x11\x00"
    return b"\xff\xd8" + app0 + sof + b"\xff\xd9"


class Writer:
    """Buffers, buffer views and accessors of a glTF document being written."""

    def __init__(self):
        self.buffers = [bytearray(), bytearray()]
        self.views, self.accessors = [], []

    def view(self, data, buffer=0, stride=None):
        """A buffer view over `data` appended to `buffer` at a 4-byte boundary."""
        out = self.buffers[buffer]
        out.extend(b"\x00" * (-len(out) % 4))
        entry = {"buffer": buffer, "byteOffset": len(out), "byteLength": len(data)}
        if stride:
            entry["byteStride"] = stride
        out.extend(data)
        self.views.append(entry)
        return len(self.views) - 1

    def accessor(self, view, component, kind, count, offset=0, normalized=False):
        """An accessor over view `view`."""
        entry = {
            "bufferView": view,
            "componentType": component,
            "type": kind,
            "count": count,
        }
        if offset:
            entry["byteOffset"] = offset
        if normalized:
            entry["normalized"] = True
        self.accessors.append(entry)
        return len(self.accessors) - 1

    def add_sparse(self, component, kind, base, count, index_type, rows, values):
        """A sparse accessor over `base` (None: no buffer view) replacing `rows`."""
        if base is None:
            self.accessors.append({"componentType": component, "type": kind})
            index = len(self.accessors) - 1
        else:
            index = self.add(base, component, kind)
        entry = self.accessors[index]
        entry["count"] = count
        dtype = np.dtype(DTYPES[component])
        entry["sparse"] = {
            "count": len(rows),
            "indices": {
                "bufferView": self.view(rows.astype(DTYPES[index_type]).tobytes()),
                "componentType": index_type,
            },
            "values": {"bufferView": self.view(values.astype(dtype).tobytes())},
        }
        return index

    def add(self, values, component, kind, normalized=False):
        """An accessor holding `values` (matrices given row-major, written by column)."""
        dtype = np.dtype(DTYPES[component])
        values = np.asarray(values)
        if kind.startswith("MAT"):
            n = SIZES[kind]
            column = n * dtype.itemsize
            pad = -column % 4
            data = bytearray()
            for matrix in values:
                for c in range(n):
                    data += matrix[:, c].astype(dtype).tobytes() + b"\x00" * pad
        else:
            data = values.astype(dtype).tobytes()
        return self.accessor(
            self.view(bytes(data)), component, kind, len(values), 0, normalized
        )


QUAD = np.array([[-1, -1, 0], [1, -1, 0], [1, 1, 0], [-1, 1, 0]], np.float32)
VALUES = {
    "positions": QUAD,
    "normals": np.tile(np.array([0, 0, 1], np.float32), (4, 1)),
    "tangents": np.tile(np.array([1, 0, 0, -1], np.float32), (4, 1)),
    "uv0": np.array([[0, 1], [1, 1], [1, 0], [0, 0]], np.float32) * np.float32(0.75),
    "uv1_raw": np.array(
        [[0, 65535], [32768, 1000], [65535, 0], [12345, 54321]], np.uint16
    ),
    "colors_raw": np.array(
        [[255, 0, 0, 255], [0, 128, 0, 64], [0, 0, 255, 1], [7, 8, 9, 10]], np.uint8
    ),
    "joints": np.array([[0, 1, 2, 3]] * 4, np.uint8),
    "weights": np.array([[0.25, 0.25, 0.25, 0.25]] * 4, np.float32),
    "target": np.array([[0, 0, 0.5]] * 4, np.float32),
    "indices_a": np.array([[0, 1, 2], [0, 2, 3]], np.uint8),
    "indices_b": np.array([[2, 3, 0]], np.uint16),
    "colors_b": np.array([[0.1, 0.2, 0.3]] * 4, np.float32),
    "unindexed": np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 0], [0, 1, 1]], np.float32
    ),
    "tri": np.array([[0, 0, 0], [2, 0, 0], [0, 3, 0]], np.float32),
    "tri_normals": np.array([[0, 0, 1]] * 3, np.float32),
    "tri_indices": np.array([[0, 1, 2]], np.uint32),
}
# one raw accessor per component type, covering every type
RAW = [
    (5120, "VEC3", True, np.array([[-128, -127, 0], [1, 64, 127]], np.int8)),
    (5121, "MAT2", False, np.array([[[1, 2], [3, 4]], [[5, 6], [7, 8]]], np.uint8)),
    (5122, "MAT3", True, np.arange(-9, 9, dtype=np.int16).reshape(2, 3, 3) * 3000),
    (5123, "SCALAR", False, np.array([0, 1, 65535], np.uint16)),
    (5125, "VEC2", False, np.array([[0, 4294967295], [7, 8]], np.uint32)),
    (5126, "MAT4", False, np.arange(32, dtype=np.float32).reshape(2, 4, 4) / 7),
    (5126, "VEC4", False, np.array([[0.5, -0.25, 1e-7, 3e5]], np.float32)),
]
# sparse accessors: component, type, base (None: zeros of count), count, index type,
# indices, values
SPARSE = [
    (
        5126,
        "VEC3",
        np.arange(15, dtype=np.float32).reshape(5, 3) / 4,
        5,
        5121,
        np.array([1, 3], np.uint8),
        np.array([[-1, -2, -3], [9, 8, 7]], np.float32),
    ),
    (
        5123,
        "SCALAR",
        None,
        6,
        5125,
        np.array([0, 5, 2], np.uint32),
        np.array([11, 22, 33], np.uint16),
    ),
]
# instances: translation, axis, angle, scale
INSTANCES = [
    ([0, 0, 0], [0, 0, 1], 0.0, [1, 1, 1]),
    ([5, 0, 0], [0, 1, 0], 0.7, [2, 2, 2]),
    ([0, -3, 1], [1, 1, 0], 2.1, [1, 0.5, 3]),
]


def quaternion(axis, angle):
    """The unit quaternion (x, y, z, w) of a rotation by `angle` about `axis`."""
    axis = np.asarray(axis, np.float64) / np.linalg.norm(axis)
    return list(axis * np.sin(angle / 2)) + [np.cos(angle / 2)]


ROOT_TRS = {
    "translation": [1.0, 2.0, 3.0],
    "rotation": quaternion([0, 1, 0], 0.5),
    "scale": [2.0, 2.0, 2.0],
}
CHILD_MATRIX = [1, 0, 0, 0, 0, 0, 1, 0, 0, -1, 0, 0, 0.5, 0.25, -4, 1]
MATERIAL = {
    "name": "every field",
    "pbrMetallicRoughness": {
        "baseColorFactor": [0.8, 0.6, 0.4, 0.9],
        "baseColorTexture": {
            "index": 0,
            "texCoord": 1,
            "extensions": {
                "KHR_texture_transform": {
                    "offset": [0.1, 0.2],
                    "rotation": 0.3,
                    "scale": [2.0, 3.0],
                    "texCoord": 0,
                }
            },
        },
        "metallicFactor": 0.25,
        "roughnessFactor": 0.75,
        "metallicRoughnessTexture": {"index": 1, "texCoord": 1},
    },
    "normalTexture": {"index": 0, "scale": 0.5},
    "occlusionTexture": {"index": 1, "strength": 0.4},
    "emissiveFactor": [0.2, 0.3, 0.4],
    "emissiveTexture": {"index": 0},
    "alphaMode": "MASK",
    "alphaCutoff": 0.3,
    "doubleSided": True,
    "extensions": {
        "KHR_materials_emissive_strength": {"emissiveStrength": 5.0},
        "KHR_materials_unlit": {},
        "KHR_materials_clearcoat": {"clearcoatFactor": 0.7},
    },
}
LIGHTS = [
    {"type": "directional", "color": [1.0, 0.9, 0.8], "intensity": 3.0},
    {"type": "point", "color": [0.5, 0.5, 1.0], "intensity": 40.0, "range": 10.0},
    {
        "type": "spot",
        "intensity": 25.0,
        "spot": {"innerConeAngle": 0.2, "outerConeAngle": 0.6},
    },
]
CAMERAS = [
    {
        "type": "perspective",
        "perspective": {"yfov": 0.8, "aspectRatio": 1.5, "znear": 0.1, "zfar": 100.0},
    },
    {
        "type": "orthographic",
        "orthographic": {"xmag": 2.0, "ymag": 1.5, "znear": 0.01, "zfar": 50.0},
    },
]
IMAGE_SIZES = {"png": (64, 32), "jpeg": (40, 20)}
STORED_TRIANGLES = 6
DRAWN_TRIANGLES = 15


def _quad_primitives(w):
    """Mesh 0's primitives: every attribute, u16 indices, unindexed, and a line strip."""
    v = VALUES
    interleaved = np.zeros((4, 8), np.float32)
    interleaved[:, :3], interleaved[:, 3:6] = v["positions"], v["normals"]
    view = w.view(interleaved.tobytes(), stride=32)
    position = w.accessor(view, 5126, "VEC3", 4)
    normal = w.accessor(view, 5126, "VEC3", 4, offset=12)
    a = {
        "attributes": {
            "POSITION": position,
            "NORMAL": normal,
            "TANGENT": w.add(v["tangents"], 5126, "VEC4"),
            "TEXCOORD_0": w.add(v["uv0"], 5126, "VEC2"),
            "TEXCOORD_1": w.add(v["uv1_raw"], 5123, "VEC2", True),
            "COLOR_0": w.add(v["colors_raw"], 5121, "VEC4", True),
            "JOINTS_0": w.add(v["joints"], 5121, "VEC4"),
            "WEIGHTS_0": w.add(v["weights"], 5126, "VEC4"),
        },
        "indices": w.add(v["indices_a"].ravel(), 5121, "SCALAR"),
        "material": 0,
        "targets": [{"POSITION": w.add(v["target"], 5126, "VEC3")}],
    }
    b = {
        "attributes": {
            "POSITION": position,
            "COLOR_0": w.add(v["colors_b"], 5126, "VEC3"),
        },
        "indices": w.add(v["indices_b"].ravel(), 5123, "SCALAR"),
        "material": 1,
    }
    c = {"attributes": {"POSITION": w.add(v["unindexed"], 5126, "VEC3")}}
    lines = {"attributes": {"POSITION": position}, "mode": 3}
    return [a, b, c, lines]


def _instancing(w):
    """The EXT_mesh_gpu_instancing extension of the instanced node."""
    t = np.array([i[0] for i in INSTANCES], np.float32)
    r = np.array([quaternion(i[1], i[2]) for i in INSTANCES], np.float32)
    s = np.array([i[3] for i in INSTANCES], np.float32)
    attributes = {
        "TRANSLATION": w.add(t, 5126, "VEC3"),
        "ROTATION": w.add(r, 5126, "VEC4"),
        "SCALE": w.add(s, 5126, "VEC3"),
    }
    return {"EXT_mesh_gpu_instancing": {"attributes": attributes}}


def _nodes(w):
    """The node list: a root, a two-level tree, instanced, lights, cameras, moving, outside."""
    light = [{"KHR_lights_punctual": {"light": i}} for i in range(3)]
    return [
        {"name": "root", **ROOT_TRS, "children": [1, 2, 3, 4, 6, 7, 8, 9, 11, 12]},
        {"name": "child", "matrix": CHILD_MATRIX, "mesh": 0, "children": [5]},
        {
            "name": "copies",
            "mesh": 1,
            "translation": [0, 1, 0],
            "extensions": _instancing(w),
        },
        {
            "name": "sun",
            "extensions": light[0],
            "rotation": quaternion([1, 0, 0], -1.0),
        },
        {"name": "lamp", "extensions": light[1], "translation": [0, 4, 0]},
        {"name": "grandchild", "mesh": 1, "scale": [1, 1, 3]},
        {"name": "spot", "extensions": light[2]},
        {"name": "cam_persp", "camera": 0, "translation": [0, 1, 8]},
        {"name": "cam_ortho", "camera": 1},
        {"name": "animated", "mesh": 0, "children": [10]},
        {"name": "rider"},
        {"name": "skinned", "skin": 0},
        {"name": "mirror", "mesh": 1, "scale": [-1, 1, 1]},
        {"name": "outside", "mesh": 1},
    ]


def document():
    """The glTF document and its writer (buffer 0 the main bytes, buffer 1 the images)."""
    w = Writer()
    raw = [w.add(values, c, kind, norm) for c, kind, norm, values in RAW]
    raw += [w.add_sparse(*case) for case in SPARSE]
    quad = _quad_primitives(w)
    tri = {
        "attributes": {
            "POSITION": w.add(VALUES["tri"], 5126, "VEC3"),
            "NORMAL": w.add(VALUES["tri_normals"], 5126, "VEC3"),
        },
        "indices": w.add(VALUES["tri_indices"].ravel(), 5125, "SCALAR"),
        "material": 0,
    }
    png_view = w.view(png_bytes(*IMAGE_SIZES["png"]), buffer=1)
    doc = {
        "asset": {"version": "2.0"},
        "extensionsUsed": [
            "KHR_lights_punctual",
            "KHR_materials_emissive_strength",
            "KHR_texture_transform",
            "KHR_materials_unlit",
            "KHR_materials_clearcoat",
            "EXT_mesh_gpu_instancing",
        ],
        "extensionsRequired": [
            "KHR_texture_transform",
            "KHR_materials_pbrSpecularGlossiness",
        ],
        "scene": 0,
        "scenes": [{"nodes": [0]}, {"nodes": [13]}],
        "nodes": _nodes(w),
        "meshes": [
            {"name": "quad", "primitives": quad},
            {"name": "tri", "primitives": [tri]},
        ],
        "materials": [MATERIAL, {"name": "glass", "alphaMode": "BLEND"}],
        "textures": [{"source": 0, "sampler": 0}, {"source": 1}],
        "samplers": [
            {"wrapS": 33071, "wrapT": 33648, "magFilter": 9728, "minFilter": 9987}
        ],
        "images": [
            {"name": "png", "bufferView": png_view, "mimeType": "image/png"},
            {"name": "jpeg", "uri": "tex%20one.jpg"},
        ],
        "cameras": CAMERAS,
        "extensions": {"KHR_lights_punctual": {"lights": LIGHTS}},
        "animations": [
            {
                "channels": [
                    {"sampler": 0, "target": {"node": 9, "path": "translation"}}
                ],
                "samplers": [{"input": raw[3], "output": raw[0]}],
            }
        ],
        "skins": [{"joints": [11]}],
    }
    return doc, w, raw


def _finish(doc, w, main_uri):
    """The document with its buffer entries: buffer 0 at `main_uri` (None: BIN chunk)."""
    doc = copy.deepcopy(doc)
    doc["bufferViews"], doc["accessors"] = w.views, w.accessors
    images = bytes(w.buffers[1])
    doc["buffers"] = [
        {"byteLength": len(w.buffers[0])},
        {
            "byteLength": len(images),
            "uri": "data:application/octet-stream;base64,"
            + base64.b64encode(images).decode(),
        },
    ]
    if main_uri:
        doc["buffers"][0]["uri"] = main_uri
    return doc


def write_glb(path, doc, w):
    """Writes a `.glb`: JSON chunk, BIN chunk (buffer 0), images as a data URI buffer."""
    text = json.dumps(_finish(doc, w, None)).encode()
    text += b" " * (-len(text) % 4)
    binary = bytes(w.buffers[0]) + b"\x00" * (-len(w.buffers[0]) % 4)
    length = 12 + 8 + len(text) + 8 + len(binary)
    with open(path, "wb") as out:
        out.write(struct.pack("<III", 0x46546C67, 2, length))
        out.write(struct.pack("<II", len(text), 0x4E4F534A) + text)
        out.write(struct.pack("<II", len(binary), 0x004E4942) + binary)
    (path.parent / "tex one.jpg").write_bytes(jpeg_bytes(*IMAGE_SIZES["jpeg"]))


def write_gltf(path, doc, w):
    """Writes a `.gltf` with buffer 0 in an external `.bin` and the images in a data URI."""
    name = path.stem + ".bin"
    (path.parent / name).write_bytes(bytes(w.buffers[0]))
    path.write_text(json.dumps(_finish(doc, w, name)))
    (path.parent / "tex one.jpg").write_bytes(jpeg_bytes(*IMAGE_SIZES["jpeg"]))
