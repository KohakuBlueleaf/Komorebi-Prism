"""Writes the check's `.glb`: a quad per material (one material per row of the mapping and
one falling to each later row), a quad without uv0, a textured quad with a transform, a
camera under a moved parent, a sun, a lamp and a spot."""

import numpy as np

from checks.scene_description import build
from prism_reference.io.png import write_png

# The 2 x 2 colour texture, rows top to bottom as the PNG stores them.
COLOURS = np.array(
    [[[255, 0, 0], [0, 255, 0]], [[0, 0, 255], [255, 255, 0]]], dtype=np.uint8
)
NORMALS = np.array([[[128, 128, 255]] * 2] * 2, dtype=np.uint8)
TRANSFORM = {"offset": [1.1, -0.3], "rotation": 0.4, "scale": [2.0, 0.5]}
# Where each corner of the textured quad lands after the transform, in glTF's uv.
TARGETS = np.array([[0.25, 0.25], [1.75, 0.25], [0.75, -0.25], [0.25, 2.75]])
QUAD_INDICES = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.uint16)
CAMERA = {"yfov": 0.7, "aspectRatio": 1.5, "znear": 0.05}
CAMERA_PARENT = [1.0, 0.0, 0.0]
CAMERA_TRS = {"translation": [0.5, 1.0, 6.0], "axis": [0.3, 1.0, 0.2], "angle": 0.6}

# name, the glTF material, then the expected kind, base, slots, exponent, specular,
# transmission (texture 0: the colour image as colour, texture 1: the normal image).
B = {"index": 0}
N = {"index": 1}
KINDS = [
    (
        "emissive factor",
        {
            "emissiveFactor": [1.0, 0.2, 0.1],
            "alphaMode": "BLEND",
            "pbr": {"baseColorTexture": B, "roughnessFactor": 0.5},
        },
        ("emissive", [1.0, 0.2, 0.1], [-1, -1, -1, -1], 30, [0.04] * 3, [0.0] * 3),
    ),
    (
        "emissive texture",
        {
            "emissiveTexture": B,
            "emissiveFactor": [0.3, 0.3, 0.3],
            "pbr": {"roughnessFactor": 0.5},
        },
        ("emissive", [0.3, 0.3, 0.3], [0, -1, -1, -1], 30, [0.04] * 3, [0.0] * 3),
    ),
    (
        "emissive strength",
        {
            "emissiveFactor": [0.1, 0.0, 0.0],
            "extensions": {"KHR_materials_emissive_strength": {"emissiveStrength": 6}},
            "pbr": {},
        },
        ("emissive", [0.6, 0.0, 0.0], [-1, -1, -1, -1], 1, [0.04] * 3, [0.0] * 3),
    ),
    (
        "blend",
        {
            "alphaMode": "BLEND",
            "pbr": {
                "baseColorFactor": [0.5, 0.6, 0.7, 0.25],
                "baseColorTexture": B,
                "roughnessFactor": 0.5,
            },
            "normalTexture": N,
        },
        ("transparent", [0.5, 0.6, 0.7], [0, -1, -1, -1], 30, [0.01] * 3, [0.75] * 3),
    ),
    (
        "transmission",
        {
            "extensions": {"KHR_materials_transmission": {"transmissionFactor": 0.8}},
            "pbr": {"baseColorFactor": [0.5, 0.5, 1.0, 1.0], "metallicFactor": 0.0},
        },
        (
            "transparent",
            [0.5, 0.5, 1.0],
            [-1, -1, -1, -1],
            1,
            [0.04] * 3,
            [0.4, 0.4, 0.8],
        ),
    ),
    (
        "transmission metal",
        {
            "extensions": {"KHR_materials_transmission": {"transmissionFactor": 0.8}},
            "pbr": {"baseColorFactor": [0.5, 0.5, 1.0, 1.0], "metallicFactor": 1.0},
        },
        ("transparent", [0.0] * 3, [-1, -1, -1, -1], 1, [0.5, 0.5, 1.0], [0.0] * 3),
    ),
    (
        "flat mask",
        {"alphaMode": "MASK", "normalTexture": N, "pbr": {"roughnessFactor": 0.5}},
        ("flat", [1.0, 1.0, 1.0], [-1, -1, -1, -1], 30, [0.04] * 3, [0.0] * 3),
    ),
    (
        "masked",
        {
            "alphaMode": "MASK",
            "normalTexture": N,
            "pbr": {"baseColorTexture": B, "roughnessFactor": 0.5},
        },
        ("masked", [1.0, 1.0, 1.0], [0, -1, -1, -1], 30, [0.04] * 3, [0.0] * 3),
    ),
    (
        "lit",
        {
            "normalTexture": N,
            "pbr": {
                "baseColorFactor": [0.9, 0.8, 0.7, 1.0],
                "baseColorTexture": B,
                "metallicFactor": 1.0,
                "roughnessFactor": 0.5,
            },
        },
        ("lit", [0.9, 0.8, 0.7], [0, -1, 1, -1], 30, [0.9, 0.8, 0.7], [0.0] * 3),
    ),
    (
        "textured",
        {
            "extensions": {"KHR_materials_transmission": {"transmissionFactor": 0.0}},
            "pbr": {
                "baseColorTexture": B
                | {"extensions": {"KHR_texture_transform": TRANSFORM}},
                "roughnessFactor": 0.5,
            },
        },
        ("textured", [1.0, 1.0, 1.0], [0, -1, -1, -1], 30, [0.04] * 3, [0.0] * 3),
    ),
]
SHADOWS = {"blend": [0.75] * 3}  # a row's shadow when not 0: 1 - its coverage
TEXTURED = len(KINDS)  # the textured material's row (row 0 is "(flat)")
NO_UV = ("textured (no uv0)", "flat", [1.0, 1.0, 1.0], [-1, -1, -1, -1])


def gltf_material(name, spec):
    """The glTF material entry of a KINDS row's spec."""
    entry = {"name": name, "pbrMetallicRoughness": {"metallicFactor": 0.0}}
    entry["pbrMetallicRoughness"] |= spec["pbr"]
    entry |= {k: v for k, v in spec.items() if k != "pbr"}
    return entry


def corner_uv0():
    """The textured quad's uv0: TARGETS through the inverse of TRANSFORM."""
    c, s = np.cos(TRANSFORM["rotation"]), np.sin(TRANSFORM["rotation"])
    shifted = TARGETS - TRANSFORM["offset"]
    rotated = np.stack(
        [c * shifted[:, 0] - s * shifted[:, 1], s * shifted[:, 0] + c * shifted[:, 1]],
        1,
    )
    return (rotated / TRANSFORM["scale"]).astype(np.float32)


def png(folder, name, pixels):
    """The bytes of a PNG of `pixels` written into `folder`."""
    path = folder / f"{name}.png"
    write_png(path, pixels)
    return path.read_bytes()


def write(path):
    """Writes the check's `.glb` at `path`."""
    w = build.Writer()
    quad = build.QUAD
    position = w.add(quad, 5126, "VEC3")
    plain_uv = w.add(
        np.array([[0, 1], [1, 1], [1, 0], [0, 0]], np.float32), 5126, "VEC2"
    )
    indices = w.add(QUAD_INDICES.ravel(), 5123, "SCALAR")

    def primitive(material, uv):
        attributes = {"POSITION": position}
        if uv is not None:
            attributes["TEXCOORD_0"] = uv
        return {"attributes": attributes, "indices": indices, "material": material}

    textured = primitive(TEXTURED - 1, w.add(corner_uv0(), 5126, "VEC2"))
    others = [primitive(m, plain_uv) for m in range(len(KINDS))]
    others.append(primitive(TEXTURED - 1, None))
    images = [
        {
            "bufferView": w.view(png(path.parent, n, p), buffer=1),
            "mimeType": "image/png",
        }
        for n, p in (("colours", COLOURS), ("normals", NORMALS))
    ]
    t, axis, angle = CAMERA_TRS["translation"], CAMERA_TRS["axis"], CAMERA_TRS["angle"]
    lights = [
        {"type": "directional", "color": [1.0, 0.9, 0.8]},
        {"type": "point", "color": [0.2, 0.4, 1.0]},
        {"type": "spot", "color": [1.0, 1.0, 1.0]},
    ]
    doc = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0, 1, 2, 4, 5, 6]}],
        "nodes": [
            {"name": "textured quad", "mesh": 0},
            {"name": "the rest", "mesh": 1, "translation": [0.0, 0.0, -3.0]},
            {"name": "rig", "translation": CAMERA_PARENT, "children": [3]},
            {
                "name": "view",
                "camera": 0,
                "translation": t,
                "rotation": build.quaternion(axis, angle),
            },
            {
                "name": "sun",
                "rotation": build.quaternion([1, 0, 0], -1.0),
                "extensions": {"KHR_lights_punctual": {"light": 0}},
            },
            {
                "name": "lamp",
                "translation": [0.0, 2.0, 1.0],
                "extensions": {"KHR_lights_punctual": {"light": 1}},
            },
            {"name": "spot", "extensions": {"KHR_lights_punctual": {"light": 2}}},
        ],
        "meshes": [{"primitives": [textured]}, {"primitives": others}],
        "materials": [gltf_material(name, spec) for name, spec, _ in KINDS],
        "textures": [{"source": 0}, {"source": 1}],
        "images": images,
        "cameras": [{"type": "perspective", "perspective": CAMERA}],
        "extensions": {"KHR_lights_punctual": {"lights": lights}},
    }
    build.write_glb(path, doc, w)


def write_plain(path):
    """Writes a `.glb` without any image: a quad of one untextured material and a camera."""
    w = build.Writer()
    quad = {
        "attributes": {"POSITION": w.add(build.QUAD, 5126, "VEC3")},
        "indices": w.add(QUAD_INDICES.ravel(), 5123, "SCALAR"),
        "material": 0,
    }
    doc = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0, 1]}],
        "nodes": [
            {"name": "quad", "mesh": 0},
            {"name": "view", "camera": 0, "translation": [0.0, 0.0, 4.0]},
        ],
        "meshes": [{"primitives": [quad]}],
        "materials": [{"name": "plain", "pbrMetallicRoughness": {"metallicFactor": 0}}],
        "cameras": [{"type": "perspective", "perspective": CAMERA}],
    }
    build.write_glb(path, doc, w)
