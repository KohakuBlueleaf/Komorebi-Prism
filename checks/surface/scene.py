"""The planes of a quad facing the camera, written as a `.glb` here (a 4 x 4 base colour
texture, a normal map tilting its right half, vertex colours, the material's factors),
against values computed here."""

import numpy as np

from checks.scene_description import build
from checks.surface.record import same
from prism_reference.io.png import write_png
from prism_reference.material.surface import surface
from prism_reference.scene.importers import gltf

SIZE = (80, 60)
HALF_HEIGHT = 0.4  # tan(yfov / 2)
DISTANCE = 3.0
TILT = np.radians(30.0)
NORMAL_SCALE = 0.8
FACTOR = [0.9, 0.8, 0.7, 0.6]
METALLIC, ROUGHNESS = 0.25, 0.6
EMISSIVE, EMISSIVE_STRENGTH = [0.1, 0.2, 0.3], 2.0
LEFT_COLOUR, RIGHT_COLOUR = [0.5, 1.0, 1.0, 1.0], [1.0, 0.5, 1.0, 1.0]
QUAD = np.array([[-1, -1, 0], [1, -1, 0], [1, 1, 0], [-1, 1, 0]], np.float32)
QUAD_UV = np.array([[0, 1], [1, 1], [1, 0], [0, 0]], np.float32)
QUAD_INDICES = np.array([[0, 1, 2], [0, 2, 3]], np.uint16)
BASE = np.random.default_rng(11).integers(0, 256, size=(4, 4, 3)).astype(np.uint8)
FLAT = np.array([128, 128, 255], np.uint8)
BENT = np.rint((np.array([np.sin(TILT), 0, np.cos(TILT)]) * 0.5 + 0.5) * 255)
NORMALS = np.zeros((4, 4, 3), np.uint8)
NORMALS[:, :2], NORMALS[:, 2:] = FLAT, BENT.astype(np.uint8)
# Lens cases: the camera's fields and the focal length across, over tan(yfov / 2).
LENSES = (
    ({"aspect": 2.0, "sensor_fit": "HORIZONTAL", "shift_x": 0.1, "shift_y": 0.05}, 2.0),
    ({"aspect": 0.75, "sensor_fit": "AUTO", "shift_x": -0.05, "shift_y": 0.0}, 1.0),
)


def png(folder, name, image):
    """The bytes of a PNG of `image` written into `folder`."""
    path = folder / f"{name}.png"
    write_png(path, image)
    return path.read_bytes()


def write(path):
    """Writes the quad, its material and its camera as a `.glb` at `path`."""
    w = build.Writer()
    colours = np.array([LEFT_COLOUR, RIGHT_COLOUR, RIGHT_COLOUR, LEFT_COLOUR])
    primitive = {
        "attributes": {
            "POSITION": w.add(QUAD, 5126, "VEC3"),
            "NORMAL": w.add(
                np.tile([0.0, 0, 1], (4, 1)).astype(np.float32), 5126, "VEC3"
            ),
            "TEXCOORD_0": w.add(QUAD_UV, 5126, "VEC2"),
            "COLOR_0": w.add(colours.astype(np.float32), 5126, "VEC4"),
        },
        "indices": w.add(QUAD_INDICES.ravel(), 5123, "SCALAR"),
        "material": 0,
    }
    images = [
        {
            "bufferView": w.view(png(path.parent, n, p), buffer=1),
            "mimeType": "image/png",
        }
        for n, p in (("base", BASE), ("normals", NORMALS))
    ]
    material = {
        "name": "quad",
        "pbrMetallicRoughness": {
            "baseColorFactor": FACTOR,
            "baseColorTexture": {"index": 0},
            "metallicFactor": METALLIC,
            "roughnessFactor": ROUGHNESS,
        },
        "normalTexture": {"index": 1, "scale": NORMAL_SCALE},
        "emissiveFactor": EMISSIVE,
        "extensions": {
            "KHR_materials_emissive_strength": {"emissiveStrength": EMISSIVE_STRENGTH}
        },
    }
    camera = {"yfov": 2 * np.arctan(HALF_HEIGHT), "znear": 0.05}
    doc = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0, 1]}],
        "nodes": [
            {"name": "quad", "mesh": 0},
            {"name": "view", "camera": 0, "translation": [0.0, 0.0, DISTANCE]},
        ],
        "meshes": [{"primitives": [primitive]}],
        "materials": [material],
        "textures": [{"source": 0}, {"source": 1}],
        "images": images,
        "cameras": [{"type": "perspective", "perspective": camera}],
    }
    build.write_glb(path, doc, w)


def srgb_decoded(byte):
    """The standard sRGB transfer undone."""
    c = byte / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def bilinear(image, u, v):
    """The bilinear value of a (4, 4, C) image at (u, v), repeating."""
    x, y = u * 4 - 0.5, v * 4 - 0.5
    x0, y0 = int(np.floor(x)), int(np.floor(y))
    fx, fy = x - x0, y - y0

    def at(i, j):
        return image[j % 4, i % 4]

    top = at(x0, y0) * (1 - fx) + at(x0 + 1, y0) * fx
    bottom = at(x0, y0 + 1) * (1 - fx) + at(x0 + 1, y0 + 1) * fx
    return top * (1 - fy) + bottom * fy


def tangent_normal(byte):
    """A normal map's bytes as the unit normal in the quad's frame (+x, +y, +z)."""
    t = byte / 255.0 * 2 - 1
    t[:2] *= NORMAL_SCALE
    return t / np.linalg.norm(t)


def expected(px, py):
    """Every plane's value at pixel (px, py), computed here."""
    focal = (SIZE[1] / 2) / HALF_HEIGHT
    x = DISTANCE * (px + 0.5 - SIZE[0] / 2) / focal
    y = DISTANCE * (SIZE[1] / 2 - (py + 0.5)) / focal
    u, v = (x + 1) / 2, (1 - y) / 2
    colour = np.array(LEFT_COLOUR) + u * (np.array(RIGHT_COLOUR) - LEFT_COLOUR)
    base = np.array(FACTOR[:3]) * colour[:3] * bilinear(srgb_decoded(BASE), u, v)
    normal = tangent_normal(NORMALS[0, 0 if u < 0.5 else 3].astype(np.float64))
    return {
        "covered": True,
        "depth": DISTANCE,
        "position": [x, y, 0.0],
        "geometric_normal": [0.0, 0.0, 1.0],
        "normal": normal,
        "base_color": base,
        "alpha": FACTOR[3] * colour[3],
        "metallic": METALLIC,
        "roughness": ROUGHNESS,
        "occlusion": 1.0,
        "emissive": np.array(EMISSIVE) * EMISSIVE_STRENGTH,
        "material": 0,
        "transparent": False,
        "uv": [u, v],
    }


def chosen_pixels():
    """Pixels whose u lies inside one half of the normal map, away from its seams."""
    focal = (SIZE[1] / 2) / HALF_HEIGHT
    found = []
    for px in range(SIZE[0]):
        u = (DISTANCE * (px + 0.5 - SIZE[0] / 2) / focal + 1) / 2
        if 0.15 < u < 0.35 or 0.65 < u < 0.85:
            found.extend((px, py) for py in (14, 23, 30, 41))
    return found[::3]


def surface_case(folder):
    """Every plane at the chosen pixels, and an uncovered corner."""
    path = folder / "surface.glb"
    write(path)
    scene = gltf.load(path)
    planes = surface(scene, 1, SIZE)
    for px, py in chosen_pixels():
        for name, want in expected(px, py).items():
            same(f"surface {name} at {px},{py}", planes[name][py, px], want, 1e-5)
    same("surface corner covered", planes["covered"][0, 0], False)
    same("surface corner material", planes["material"][0, 0], -1)
    for fields, across in LENSES:
        lens_case(scene, fields, across)


def lens_case(scene, fields, across):
    """A sensor fit at another aspect and a lens shift: the position at every covered
    pixel against the moved principal point and the kept field across (`across`
    times tan(yfov / 2))."""
    cam = scene.cameras[scene.nodes[1].camera]
    for name, value in fields.items():
        setattr(cam, name, value)
    planes = surface(scene, 1, SIZE)
    width, height = SIZE
    focal = (width / 2) / (HALF_HEIGHT * across)
    cx = width / 2 - fields["shift_x"] * width
    cy = height / 2 + fields["shift_y"] * width
    xs, ys = np.meshgrid(np.arange(width) + 0.5, np.arange(height) + 0.5)
    x, y = DISTANCE * (xs - cx) / focal, DISTANCE * (cy - ys) / focal
    inside = (np.abs(x) < 0.98) & (np.abs(y) < 0.98)
    outside = (np.abs(x) > 1.02) | (np.abs(y) > 1.02)
    fit = fields["sensor_fit"]
    same(f"lens {fit} covered inside", bool(planes["covered"][inside].all()), True)
    same(f"lens {fit} uncovered outside", bool(planes["covered"][outside].any()), False)
    want = np.stack([x[inside], y[inside], 0 * x[inside]], -1)
    same(f"lens {fit} position", planes["position"][inside], want, 1e-5)
