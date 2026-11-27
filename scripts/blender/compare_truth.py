"""Run inside Blender on `from_gltf.py`'s .blend: Cycles' light passes by lobe and the
planes that register a pixel as float32 planes in an .npz, Blender's picture as a PNG.
`blender --background <file.blend> --python compare_truth.py -- <out_stem>
--size W H [--samples N] [--camera NODE]`"""

import argparse
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import common
import numpy
import OpenImageIO

SEED = 0
# The plane's name: the pass's names in Blender's EXR (long, short) and its channels.
PASSES = {
    "combined": (("Combined",), "RGB"),
    "depth": (("Depth",), "Z"),
    "normal": (("Normal",), "XYZ"),
    "position": (("Position",), "XYZ"),
    "diffuse_direct": (("Diffuse Direct", "DiffDir"), "RGB"),
    "diffuse_indirect": (("Diffuse Indirect", "DiffInd"), "RGB"),
    "diffuse_color": (("Diffuse Color", "DiffCol"), "RGB"),
    "glossy_direct": (("Glossy Direct", "GlossDir"), "RGB"),
    "glossy_indirect": (("Glossy Indirect", "GlossInd"), "RGB"),
    "glossy_color": (("Glossy Color", "GlossCol"), "RGB"),
    "transmission_direct": (("Transmission Direct", "TransDir"), "RGB"),
    "transmission_indirect": (("Transmission Indirect", "TransInd"), "RGB"),
    "transmission_color": (("Transmission Color", "TransCol"), "RGB"),
    "emit": (("Emission", "Emit"), "RGB"),
    "environment": (("Environment", "Env"), "RGB"),
}
TURNED = ("normal", "position")
LAYER_PASSES = (
    "use_pass_z",
    "use_pass_normal",
    "use_pass_position",
    "use_pass_diffuse_direct",
    "use_pass_diffuse_indirect",
    "use_pass_diffuse_color",
    "use_pass_glossy_direct",
    "use_pass_glossy_indirect",
    "use_pass_glossy_color",
    "use_pass_transmission_direct",
    "use_pass_transmission_indirect",
    "use_pass_transmission_color",
    "use_pass_emit",
    "use_pass_environment",
)


def cycles(scene, samples):
    """Cycles on the OptiX devices, fixed samples and seed, no denoiser, the light
    settings of the file, and the passes of the comparison."""
    preferences = bpy.context.preferences.addons["cycles"].preferences
    preferences.compute_device_type = "OPTIX"
    preferences.get_devices()
    for device in preferences.devices:
        device.use = device.type == "OPTIX"
    scene.cycles.device = "GPU"
    scene.cycles.samples = samples
    scene.cycles.seed = SEED
    scene.cycles.use_animated_seed = False
    scene.cycles.use_denoising = False
    scene.cycles.use_adaptive_sampling = False
    for layer in scene.view_layers:
        for name in LAYER_PASSES:
            setattr(layer, name, True)


def chosen_camera(scene, name, size):
    """Makes the camera node `name` the scene's camera, its field of view recovered as
    `from_gltf.py` recovers the render camera's (at the render size), no shift; its
    name. None keeps the render camera."""
    if name is None:
        return scene.camera.name
    obj = bpy.data.objects.get(name)
    if obj is None or obj.type != "CAMERA":
        raise SystemExit(f"no camera object named {name!r}")
    if obj != scene.camera:
        data = obj.data
        aspect = size[0] / size[1]
        yfov = data.angle_y
        xfov = 2 * math.atan(aspect * math.tan(yfov / 2))
        data.sensor_fit = "AUTO"
        data.angle_x = max(xfov, yfov)
        data.shift_x = data.shift_y = 0.0
        scene.camera = obj
    return obj.name


def channels(path):
    """The EXR's pixels (H, W, C) float32 and {(pass, channel): number} of its layer
    with the most channels."""
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
        found[(".".join(parts[1:-1]) if len(parts) >= 2 else "", parts[-1])] = i
    return numpy.asarray(pixels, dtype=numpy.float32), found


def planes_of(exr, out):
    """Writes the passes of an EXR as float32 planes in an .npz; the missing ones."""
    pixels, found = channels(exr)
    planes, missing = {}, []
    for name, (blender_names, letters) in PASSES.items():
        numbers = None
        for blender_name in blender_names:
            numbers = [found.get((blender_name, c)) for c in letters]
            if None not in numbers:
                break
        if None in numbers:
            missing.append(name)
            continue
        plane = pixels[:, :, numbers]
        if len(numbers) == 1:
            plane = plane[:, :, 0]
        if name in TURNED:
            plane = numpy.stack([plane[..., 0], plane[..., 2], -plane[..., 1]], -1)
        planes[name] = numpy.ascontiguousarray(plane, dtype=numpy.float32)
    size = numpy.array([pixels.shape[1], pixels.shape[0]], dtype=numpy.int64)
    numpy.savez(out, size=size, **planes)
    return missing


def save(scene, path, file_format, media_type):
    """Saves the render result with the given output format."""
    settings = scene.render.image_settings
    if hasattr(settings, "media_type"):
        settings.media_type = media_type
    settings.file_format = file_format
    if file_format == "PNG":
        settings.color_mode = "RGB"
        settings.color_depth = "8"
    else:
        settings.color_depth = "32"
    bpy.data.images["Render Result"].save_render(path, scene=scene)


def main():
    """Renders the truth to the stem named on the command line."""
    parser = argparse.ArgumentParser()
    parser.add_argument("stem")
    parser.add_argument("--size", type=int, nargs=2, required=True)
    parser.add_argument("--samples", type=int, default=256)
    parser.add_argument("--camera", default=None)
    args = parser.parse_args(common.arguments())
    scene = bpy.context.scene
    if scene.camera is None:
        scene.camera = next(o for o in scene.objects if o.type == "CAMERA")
    render = scene.render
    render.engine = "CYCLES"
    render.resolution_x, render.resolution_y = args.size
    render.resolution_percentage = 100
    render.use_border = False
    render.use_file_extension = True
    camera = chosen_camera(scene, args.camera, args.size)
    cycles(scene, args.samples)
    started = time.perf_counter()
    bpy.ops.render.render(write_still=False)
    seconds = round(time.perf_counter() - started, 1)
    save(scene, args.stem + ".exr", "OPEN_EXR_MULTILAYER", "MULTI_LAYER_IMAGE")
    save(scene, args.stem + ".png", "PNG", "IMAGE")
    missing = planes_of(args.stem + ".exr", args.stem + ".npz")
    os.remove(args.stem + ".exr")
    view = scene.view_settings
    common.report(
        {
            "size": args.size,
            "samples": args.samples,
            "camera": camera,
            "seconds": seconds,
            "missing": missing,
            "bounces": scene.cycles.max_bounces,
            "display": {
                "view_transform": view.view_transform,
                "look": view.look,
                "exposure": view.exposure,
                "gamma": view.gamma,
            },
        }
    )


main()
