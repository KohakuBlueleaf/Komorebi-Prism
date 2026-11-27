"""Run inside Blender: the passes of a Cycles multilayer EXR as float32 planes in an .npz,
normals and positions in the description's axes (+Y up), the object index with its rows.
`blender --background --python planes.py -- <truth_gltf.exr> <out.npz>`"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import numpy
import OpenImageIO

# The plane's name: the pass's name in Blender's EXR and its channels in order.
PASSES = {
    "combined": ("Combined", "RGB"),
    "depth": ("Depth", "Z"),
    "normal": ("Normal", "XYZ"),
    "position": ("Position", "XYZ"),
    "diffuse_color": ("Diffuse Color", "RGB"),
    "glossy_color": ("Glossy Color", "RGB"),
    "emit": ("Emission", "RGB"),
    "uv": ("UV", "UV"),
    "object_index": ("Object Index", "X"),
}
TURNED = ("normal", "position")
ROWS = ".objects.json"  # render.py's object rows beside the EXR


def channels(path):
    """The EXR's pixels (H, W, C) float32 and {(pass, channel): number} of its layer
    with the most channels (a render layer, not the composite)."""
    source = OpenImageIO.ImageInput.open(path)
    if source is None:
        raise RuntimeError(f"{path}: {OpenImageIO.geterror()}")
    spec = source.spec()
    pixels = source.read_image(0, 0, 0, spec.nchannels, "float")
    source.close()
    names = list(spec.channelnames)
    layers = [n.split(".")[0] for n in names if n.count(".") >= 2]
    layer = max(set(layers), key=layers.count) if layers else None
    found = {}
    for i, name in enumerate(names):
        parts = name.split(".")
        if layer is not None and (len(parts) < 3 or parts[0] != layer):
            continue
        found[(parts[-2] if len(parts) >= 2 else "", parts[-1])] = i
    return numpy.asarray(pixels, dtype=numpy.float32), found


def turned(plane):
    """Blender's axes (+Z up) to the description's: (x, y, z) -> (x, z, -y)."""
    return numpy.stack([plane[..., 0], plane[..., 2], -plane[..., 1]], axis=-1)


def main():
    """Writes the planes of the EXR named on the command line."""
    exr, out = common.arguments()[:2]
    started = time.perf_counter()
    pixels, found = channels(exr)
    planes, missing = {}, []
    for name, (blender_name, letters) in PASSES.items():
        numbers = [found.get((blender_name, c)) for c in letters]
        if None in numbers:
            missing.append(name)
            continue
        plane = pixels[:, :, numbers]
        if len(numbers) == 1:
            plane = plane[:, :, 0]
        if name in TURNED:
            plane = turned(plane)
        planes[name] = numpy.ascontiguousarray(plane, dtype=numpy.float32)
    if "object_index" in planes:
        planes["object_index"] = numpy.rint(planes["object_index"]).astype(numpy.int32)
    rows_path = os.path.splitext(exr)[0] + ROWS
    if os.path.isfile(rows_path):
        with open(rows_path) as f:
            rows = json.load(f)
        planes["object_names"] = numpy.array(rows["names"])
        planes["object_types"] = numpy.array(rows["types"])
    size = numpy.array([pixels.shape[1], pixels.shape[0]], dtype=numpy.int64)
    numpy.savez(out, size=size, **planes)
    common.report(
        {
            "planes": sorted(planes),
            "missing": missing,
            "size": [int(n) for n in size],
            "seconds": round(time.perf_counter() - started, 1),
        }
    )


main()
