"""Run inside Blender: Cycles' direct-light passes of the open scene from its own camera
with indirect bounces 0, once with every light and once a light kind (and once with
none: the surfaces' own emission), each as an EXR and an .npz; the lights as Blender has
them. `blender --background <file.blend> --python light_passes.py -- <folder>
--size W H [--samples N] [--frame N] [--runs RUN ...]`"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import common
import mathutils
import numpy
import OpenImageIO

KINDS = {"POINT": "point", "SPOT": "spot", "SUN": "sun", "AREA": "area"}
# The plane's name: the pass's names in Blender's EXR (long, short) and its channels.
PASSES = {
    "combined": (("Combined",), "RGB"),
    "depth": (("Depth",), "Z"),
    "normal": (("Normal",), "XYZ"),
    "position": (("Position",), "XYZ"),
    "diffuse_direct": (("Diffuse Direct", "DiffDir"), "RGB"),
    "glossy_direct": (("Glossy Direct", "GlossDir"), "RGB"),
    "diffuse_color": (("Diffuse Color", "DiffCol"), "RGB"),
    "glossy_color": (("Glossy Color", "GlossCol"), "RGB"),
    "emit": (("Emission", "Emit"), "RGB"),
}
TURNED = ("normal", "position")
SEED = 0
DARK = "prism_dark"
NAMES_LISTED = 10


def cycles(scene, samples):
    """Cycles on the OptiX devices, fixed samples and seed, no denoiser, bounces 0, no
    data kept between renders, and the passes of the light's comparison."""
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
    scene.cycles.max_bounces = 0
    scene.render.use_persistent_data = False
    for layer in scene.view_layers:
        layer.use_pass_z = True
        layer.use_pass_normal = True
        layer.use_pass_position = True
        layer.use_pass_diffuse_direct = True
        layer.use_pass_glossy_direct = True
        layer.use_pass_diffuse_color = True
        layer.use_pass_glossy_color = True
        layer.use_pass_emit = True


def light_objects():
    """Every light object of the file with its kind and whether it renders now."""
    return [
        (o, KINDS.get(o.data.type), not o.hide_render)
        for o in bpy.data.objects
        if o.type == "LIGHT"
    ]


def turned(v):
    """Blender's axes (+Z up) to the description's: (x, y, z) -> (x, z, -y)."""
    return [float(v[0]), float(v[2]), float(-v[1])]


def node_tree(data):
    """The light's own nodes as Cycles reads them: the Emission node's strength (or a
    Light Falloff's feeding it) and whether its colour comes from a link."""
    tree = data.node_tree if getattr(data, "use_nodes", False) else None
    output = common.output_node(tree)
    if output is None or "Surface" not in output.inputs:
        return None
    found = common.upstream(output.inputs["Surface"], {"ShaderNodeEmission"})
    if not found:
        return {"emission": False}
    strength = found[0].inputs["Strength"]
    entry = {"emission": True, "color_linked": found[0].inputs["Color"].is_linked}
    entry["strength"] = None if strength.is_linked else float(strength.default_value)
    falloff = common.upstream(strength, {"ShaderNodeLightFalloff"})
    if falloff:
        entry["falloff_strength"] = float(falloff[0].inputs["Strength"].default_value)
    return entry


def described(name, data, matrix):
    """A drawn light's Blender settings, its emitting direction in the description's
    axes."""
    direction = matrix.to_3x3() @ mathutils.Vector((0.0, 0.0, -1.0))
    entry = {
        "name": name,
        "type": data.type,
        "energy": float(data.energy),
        "color": [float(c) for c in data.color],
        "exposure": float(getattr(data, "exposure", 0.0)),
        "normalize": bool(getattr(data, "normalize", True)),
        "use_nodes": bool(getattr(data, "use_nodes", False)),
        "use_temperature": bool(getattr(data, "use_temperature", False)),
        "cast_shadow": bool(getattr(data, "use_shadow", True)),
        "direction": turned(direction.normalized()),
        "nodes": node_tree(data),
    }
    if data.type in ("POINT", "SPOT"):
        entry["radius"] = float(data.shadow_soft_size)
    if data.type == "SPOT":
        entry["spot_size"] = float(data.spot_size)
        entry["spot_blend"] = float(data.spot_blend)
    if data.type == "SUN":
        entry["angle"] = float(data.angle)
    if data.type == "AREA":
        entry["shape"] = data.shape
        entry["size"] = [float(data.size), float(data.size_y)]
        entry["spread"] = float(getattr(data, "spread", 3.141592653589793))
        cycles_settings = getattr(data, "cycles", None)
        entry["is_portal"] = bool(getattr(cycles_settings, "is_portal", False))
    return entry


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


def save(scene, path):
    """Saves the render result as a 32-bit multilayer EXR."""
    settings = scene.render.image_settings
    if hasattr(settings, "media_type"):
        settings.media_type = "MULTI_LAYER_IMAGE"
    settings.file_format = "OPEN_EXR_MULTILAYER"
    settings.color_depth = "32"
    bpy.data.images["Render Result"].save_render(path, scene=scene)


def named(names):
    """The count and the first NAMES_LISTED names."""
    return {"count": len(names), "names": names[:NAMES_LISTED]}


def visibility(scene):
    """What the viewport and the render see differently: objects shown in the viewport
    but hidden in the render, objects casting no shadow, the camera's shift."""
    hidden = [
        o.name
        for o in scene.objects
        if o.hide_render and not o.hide_viewport and o.visible_get()
    ]
    no_shadow = [
        o.name
        for o in scene.objects
        if not o.hide_render and not getattr(o, "visible_shadow", True)
    ]
    camera = scene.camera.data
    return {
        "render_hidden": named(hidden),
        "no_shadow": named(no_shadow),
        "camera_shift": [float(camera.shift_x), float(camera.shift_y)],
    }


def dark_world():
    """A black world without nodes, standing for no world."""
    dark = bpy.data.worlds.get(DARK) or bpy.data.worlds.new(DARK)
    dark.color = (0.0, 0.0, 0.0)
    if hasattr(dark, "use_nodes"):
        dark.use_nodes = False
    return dark


def render_run(scene, run, objects, world, folder):
    """Renders one run (all, a kind or none) and writes cycles_<run>.exr and .npz."""
    for obj, kind, shown in objects:
        obj.hide_render = not (shown and run in ("all", kind))
    scene.world = world if run in ("all", "world") else dark_world()
    started = time.perf_counter()
    bpy.ops.render.render(write_still=False)
    seconds = round(time.perf_counter() - started, 1)
    stem = os.path.join(folder, f"cycles_{run}")
    save(scene, stem + ".exr")
    missing = planes_of(stem + ".exr", stem + ".npz")
    return {"seconds": seconds, "missing": missing}


def main():
    """Renders the runs into the folder named on the command line."""
    parser = argparse.ArgumentParser()
    parser.add_argument("folder")
    parser.add_argument("--size", type=int, nargs=2, required=True)
    parser.add_argument("--samples", type=int, default=256)
    parser.add_argument("--frame", type=int, default=None)
    parser.add_argument("--runs", nargs="*", default=None)
    args = parser.parse_args(common.arguments())
    os.makedirs(args.folder, exist_ok=True)
    scene = bpy.context.scene
    if args.frame is not None:
        scene.frame_set(args.frame)
    if scene.camera is None:
        scene.camera = next(o for o in scene.objects if o.type == "CAMERA")
    render = scene.render
    render.engine = "CYCLES"
    render.resolution_x, render.resolution_y = args.size
    render.resolution_percentage = 100
    render.use_border = False
    cycles(scene, args.samples)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    drawn = [described(n, d, m) for n, d, m in common.lights(depsgraph)]
    objects = light_objects()
    world = scene.world
    kinds = sorted({KINDS.get(d["type"]) for d in drawn} - {None})
    runs = ["all", *kinds, *(["world"] if world else []), "none"]
    runs = runs if args.runs is None else args.runs
    record = {"size": args.size, "samples": args.samples, "runs": {}}
    record["lights"] = drawn
    record["world"] = {"name": world.name if world else None}
    record["visibility"] = visibility(scene)
    with open(os.path.join(args.folder, "blender_lights.json"), "w") as f:
        json.dump(record, f, indent=1)
    for run in runs:
        record["runs"][run] = render_run(scene, run, objects, world, args.folder)
    for obj, _, shown in objects:
        obj.hide_render = not shown
    scene.world = world
    with open(os.path.join(args.folder, "blender_lights.json"), "w") as f:
        json.dump(record, f, indent=1)
    common.report({k: v for k, v in record.items() if k != "lights"})


main()
