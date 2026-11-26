"""Run inside Blender: the open scene from its own camera with its own colour management.
`blender --background <file.blend> --python render.py -- <out_stem>
--engine CYCLES|EEVEE --size W H [--samples N] [--frame N]`"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import common

ENGINES = {"CYCLES": "CYCLES", "EEVEE": "BLENDER_EEVEE"}


def cycles(scene, samples):
    """Cycles on the OptiX devices, fixed samples, no denoiser, and the passes of the
    surface's comparison: Z, Normal, Position, UV, diffuse and glossy colour, emission,
    object index."""
    preferences = bpy.context.preferences.addons["cycles"].preferences
    preferences.compute_device_type = "OPTIX"
    preferences.get_devices()
    for device in preferences.devices:
        device.use = device.type == "OPTIX"
    scene.cycles.device = "GPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = False
    scene.cycles.use_adaptive_sampling = False
    for layer in scene.view_layers:
        layer.use_pass_z = True
        layer.use_pass_normal = True
        layer.use_pass_position = True
        layer.use_pass_uv = True
        layer.use_pass_diffuse_color = True
        layer.use_pass_glossy_color = True
        layer.use_pass_emit = True
        layer.use_pass_object_index = True


def object_rows(path):
    """Numbers every object (pass index = its row, from 1; 0: none) in this session only
    and writes the rows' names and types to `path`; returns the objects left unnumbered.
    """
    rows = {"names": [""], "types": [""]}
    fixed = []
    for obj in sorted(bpy.data.objects, key=lambda o: o.name_full):
        try:
            obj.pass_index = len(rows["names"])
        except (AttributeError, RuntimeError):
            fixed.append(obj.name_full)
            continue
        rows["names"].append(obj.name_full)
        rows["types"].append(obj.type)
    with open(path, "w") as f:
        json.dump(rows, f)
    return fixed


def save(scene, path, file_format, media_type):
    """Saves the render result with the given output format."""
    settings = scene.render.image_settings
    if hasattr(settings, "media_type"):
        settings.media_type = media_type
    settings.file_format = file_format
    if file_format == "PNG":
        settings.color_mode = "RGB"
    else:
        settings.color_depth = "32"
    bpy.data.images["Render Result"].save_render(path, scene=scene)


def main():
    """Renders the open scene to the stem named on the command line."""
    parser = argparse.ArgumentParser()
    parser.add_argument("stem")
    parser.add_argument("--engine", choices=tuple(ENGINES), required=True)
    parser.add_argument("--size", type=int, nargs=2, required=True)
    parser.add_argument("--samples", type=int, default=256)
    parser.add_argument("--frame", type=int, default=None)
    args = parser.parse_args(common.arguments())
    scene = bpy.context.scene
    if args.frame is not None:
        scene.frame_set(args.frame)
    if scene.camera is None:
        scene.camera = next(o for o in scene.objects if o.type == "CAMERA")
    render = scene.render
    render.engine = ENGINES[args.engine]
    render.resolution_x, render.resolution_y = args.size
    render.resolution_percentage = 100
    render.use_border = False
    render.use_file_extension = True
    unnumbered = []
    if args.engine == "CYCLES":
        cycles(scene, args.samples)
        unnumbered = object_rows(args.stem + ".objects.json")
    started = time.perf_counter()
    bpy.ops.render.render(write_still=False)
    seconds = round(time.perf_counter() - started, 1)
    if args.engine == "CYCLES":
        save(scene, args.stem + ".exr", "OPEN_EXR_MULTILAYER", "MULTI_LAYER_IMAGE")
    save(scene, args.stem + ".png", "PNG", "IMAGE")
    common.report(
        {
            "engine": args.engine,
            "size": args.size,
            "samples": args.samples if args.engine == "CYCLES" else None,
            "seconds": seconds,
            "objects_unnumbered": len(unnumbered),
        }
    )


main()
