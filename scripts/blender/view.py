"""Run inside Blender: a view transform (and look) as this Blender's OpenColorIO
evaluates it, written as `<stem>.view.npz`: its operations up to the last 3D table
baked into one cube on their log2 domain, the per-channel tail after it as the
display's thresholds; and a linear picture through Blender's own view transform.
`blender --background --python view.py -- sidecar <stem.prism.json>`
`blender --background --python view.py -- tables <out.npz> <view> <look> [<display>]`
`blender --background --python view.py -- pictures <linear.npy> <out_dir> <view> <look>`
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(1, os.path.join(os.path.dirname(os.path.dirname(HERE)), "src"))

import bpy
import common
import numpy
import PyOpenColorIO as ocio

from prism_reference.post.view import ENTRY_ONE, TABLE_WORDS, VIEW_SUFFIX, view8

NO_LOOK = ("", "None")
F = numpy.float32
LATTICE = 65  # the cube's nodes an axis, unless the body is one table on the domain
NEGATIVE_ZERO = 0x80000000  # the thresholds' word 0, never read
SELF_SEED, SELF_COLOURS = 1, 1 << 18  # the file's own check: random HDR colours
SELF_STOPS = (-12.0, 8.0)


class Unsupported(Exception):
    """A chain the form does not hold."""


def config():
    """The OpenColorIO configuration this Blender uses ($OCIO, else its own)."""
    path = os.environ.get("OCIO") or bpy.utils.system_resource(
        "DATAFILES", path=os.path.join("colormanagement", "config.ocio")
    )
    return ocio.Config.CreateFromFile(path)


def processor(cfg, display, view, look):
    """The processor from the scene linear role to `display` through `view` and
    `look`, optimized as Blender's CPU path is."""
    source = cfg.getColorSpace(ocio.ROLE_SCENE_LINEAR).getName()
    shown = ocio.DisplayViewTransform(src=source, display=display, view=view)
    steps = [shown]
    if look not in NO_LOOK:
        steps.insert(0, ocio.LookTransform(src=source, dst=source, looks=look))
    whole = cfg.getProcessor(ocio.GroupTransform(steps))
    return whole.getOptimizedProcessor(ocio.OPTIMIZATION_DEFAULT)


def cpu(cfg, operations):
    """The CPU processor of a list of operations."""
    group = cfg.getProcessor(ocio.GroupTransform(operations))
    return group.getOptimizedProcessor(
        ocio.OPTIMIZATION_DEFAULT
    ).getDefaultCPUProcessor()


def applied(evaluate, x):
    """`evaluate` (a CPU processor) on float32 RGB (..., 3)."""
    flat = numpy.ascontiguousarray(numpy.asarray(x, F).reshape(-1, 3)).copy()
    evaluate.applyRGB(flat)
    return flat.reshape(numpy.shape(x))


def domain(operations):
    """The matrix before the first log2, the log2's range [low, high] that the scale
    after it maps to [0, 1], and the count of these operations."""
    names = [type(op).__name__ for op in operations]
    matrix, k = numpy.eye(3), 0
    while names[k] == "MatrixTransform":
        m = numpy.array(operations[k].getMatrix()).reshape(4, 4)
        if numpy.any(operations[k].getOffset()[:3]):
            raise Unsupported("an offset before the logarithm")
        matrix, k = m[:3, :3] @ matrix, k + 1
    after = operations[k + 1] if k + 1 < len(operations) else None
    if names[k] != "LogTransform" or operations[k].getBase() != 2 or after is None:
        raise Unsupported("no log2 then a scale before the 3D table")
    m = numpy.array(after.getMatrix()).reshape(4, 4)
    offset = numpy.array(after.getOffset())
    scale = m[0, 0]
    if not (
        numpy.allclose(m[:3, :3], scale * numpy.eye(3)) and numpy.ptp(offset[:3]) == 0
    ):
        raise Unsupported("the log2's scale differs between channels")
    return matrix, -offset[0] / scale, (1 - offset[0]) / scale, k + 2


def bake(cfg, body, matrix, low, high, lattice):
    """The body's values at the cube's `lattice`^3 nodes, as 16-bit entries."""
    g = numpy.linspace(0.0, 1.0, lattice)
    nodes = numpy.stack(numpy.meshgrid(g, g, g, indexing="ij"), -1).reshape(-1, 3)
    linear = (2.0 ** (nodes * (high - low) + low)) @ numpy.linalg.inv(matrix).T
    values = applied(cpu(cfg, body), linear)
    entries = numpy.rint(numpy.clip(values, 0.0, 1.0) * ENTRY_ONE)
    return entries.astype(numpy.uint16).reshape(lattice, lattice, lattice, 3)


def thresholds(cfg, tail):
    """Word k (1 to 255) the bits of the smallest float32 in [0, 1] whose byte by the
    tail is k; Unsupported when the tail differs between channels or falls."""
    evaluate = cpu(cfg, tail)

    def byte(bits):
        v = numpy.repeat(bits.astype(numpy.uint32).view(F)[:, None], 3, 1)
        out = applied(evaluate, v)
        if not (
            numpy.all(out[:, 0] == out[:, 1]) and numpy.all(out[:, 0] == out[:, 2])
        ):
            raise Unsupported("a tail that differs between channels")
        return numpy.rint(numpy.clip(out[:, 0], 0.0, 1.0) * 255)

    one = int(F(1.0).view(numpy.uint32))
    wanted = numpy.arange(1, TABLE_WORDS)
    low = numpy.zeros(TABLE_WORDS - 1, numpy.int64)
    high = numpy.full(TABLE_WORDS - 1, one, numpy.int64)
    while (low < high).any():
        middle = (low + high) // 2
        reached = byte(middle) >= wanted
        high, low = numpy.where(reached, middle, high), numpy.where(
            reached, low, middle + 1
        )
    if numpy.any(numpy.diff(byte(numpy.arange(0, one, 997))) < 0):
        raise Unsupported("a tail that falls")
    return numpy.concatenate([[NEGATIVE_ZERO], low]).astype(numpy.uint32)


def form(cfg, display, view, look):
    """{name: array} of the view's file."""
    operations = list(processor(cfg, display, view, look).createGroupTransform())
    names = [type(op).__name__ for op in operations]
    tables = [i for i, name in enumerate(names) if name == "Lut3DTransform"]
    record = {"matrix": numpy.eye(3), "low": numpy.array(0.0), "high": numpy.array(0.0)}
    record["cube"] = numpy.zeros(0, numpy.uint16)
    if tables:
        body, tail = operations[: tables[-1] + 1], operations[tables[-1] + 1 :]
        matrix, low, high, ahead = domain(operations)
        alone = tables[-1] == ahead  # the body is the domain's operations and one table
        lattice = operations[tables[-1]].getGridSize() if alone else LATTICE
        record.update(matrix=matrix, low=numpy.array(low), high=numpy.array(high))
        record["cube"] = bake(cfg, body, matrix, low, high, lattice)
    else:
        tail = operations
    record["thresholds"] = thresholds(cfg, tail)
    return record


def own_check(cfg, display, view, look, path):
    """The file against Blender's OpenColorIO on random HDR colours: a note of the
    largest 8-bit difference and the share of channels over 1."""
    rng = numpy.random.default_rng(SELF_SEED)
    scale = 2.0 ** rng.uniform(*SELF_STOPS, (SELF_COLOURS, 1))
    colours = (rng.random((SELF_COLOURS, 3)) * scale).astype(F)
    truth = applied(
        processor(cfg, display, view, look).getDefaultCPUProcessor(), colours
    )
    with numpy.load(path) as f:
        cube = f["cube"]
        made = {
            "matrix": f["matrix"].astype(F),
            "low": float(f["low"]),
            "high": float(f["high"]),
            "cube": cube if cube.size else None,
            "thresholds": f["thresholds"],
        }
    ours = view8(made, colours).astype(numpy.int16)
    theirs = numpy.rint(numpy.clip(truth, 0.0, 1.0) * 255).astype(numpy.int16)
    d = numpy.abs(ours - theirs)
    return (
        f"against Blender's OpenColorIO on {SELF_COLOURS} random colours: largest "
        f"difference {int(d.max())} in 8 bits, {100 * float(numpy.mean(d > 1)):.3f} % "
        "of channels over 1"
    )


def write(path, display, view, look):
    """The view's file written to `path`; its name (None when not written) and the
    notes."""
    cfg = config()
    try:
        record = form(cfg, display, view, look)
    except Unsupported as error:
        return None, [f"view transform {view!r}, look {look!r}: {error}; not written"]
    record |= {
        "view": numpy.array(view),
        "look": numpy.array(look),
        "display": numpy.array(display),
        "blender": numpy.array(bpy.app.version_string),
        "notes": numpy.array([], dtype=str),
    }
    with open(path, "wb") as f:
        numpy.savez_compressed(f, **record)
    notes = [own_check(cfg, display, view, look, path)]
    record["notes"] = numpy.array(notes, dtype=str)
    with open(path, "wb") as f:
        numpy.savez_compressed(f, **record)
    return os.path.basename(path), notes


def for_sidecar(path):
    """The view's file of a sidecar written beside it and named in its `render`."""
    with open(path) as f:
        record = json.load(f)
    render = record["render"]
    stem = path[: -len(".prism.json")]
    display = render.get("display") or bpy.context.scene.display_settings.display_device
    name, notes = write(
        stem + VIEW_SUFFIX, display, render["view_transform"], render["look"]
    )
    render["display"], render["view_tables"], render["view_notes"] = (
        display,
        name,
        notes,
    )
    with open(path, "w") as f:
        json.dump(record, f, indent=1)
    return {"view_tables": name, "notes": notes}


def pictures(source, folder, view, look):
    """A linear picture (H, W, 3) through Blender's own view transform: its 8-bit
    save (no dither) and OpenColorIO's float values, as .npy in `folder`."""
    pixels = numpy.load(source).astype(F)
    h, w, _ = pixels.shape
    image = bpy.data.images.new("linear", w, h, alpha=True, float_buffer=True)
    image.colorspace_settings.name = (
        config().getColorSpace(ocio.ROLE_SCENE_LINEAR).getName()
    )
    rgba = numpy.concatenate([pixels[::-1], numpy.ones((h, w, 1), F)], -1)
    image.pixels.foreach_set(rgba.ravel())
    scene = bpy.context.scene
    scene.render.dither_intensity = 0.0
    settings = scene.render.image_settings
    settings.file_format, settings.color_depth, settings.color_mode = "PNG", "8", "RGB"
    scene.view_settings.view_transform = view
    scene.view_settings.look = look if look not in NO_LOOK else "None"
    scene.view_settings.exposure, scene.view_settings.gamma = 0.0, 1.0
    scene.view_settings.use_curve_mapping = False
    png = os.path.join(folder, "blender.png")
    image.save_render(png, scene=scene)
    saved = bpy.data.images.load(png)
    shown = numpy.array(saved.pixels[:], F).reshape(h, w, saved.channels)[::-1, :, :3]
    numpy.save(
        os.path.join(folder, "blender.npy"), numpy.rint(shown * 255).astype("u1")
    )
    display = scene.display_settings.display_device
    evaluate = processor(config(), display, view, look).getDefaultCPUProcessor()
    numpy.save(os.path.join(folder, "ocio.npy"), applied(evaluate, pixels))
    return {"display": display, "size": [w, h]}


def main():
    """The mode named on the command line."""
    parser = argparse.ArgumentParser()
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("sidecar").add_argument("path")
    one = modes.add_parser("tables")
    for name in ("out", "view", "look"):
        one.add_argument(name)
    one.add_argument("display", nargs="?", default="sRGB")
    shown = modes.add_parser("pictures")
    for name in ("source", "folder", "view", "look"):
        shown.add_argument(name)
    args = parser.parse_args(common.arguments())
    if args.mode == "sidecar":
        common.report(for_sidecar(args.path))
    elif args.mode == "tables":
        name, notes = write(args.out, args.display, args.view, args.look)
        common.report({"view_tables": name, "notes": notes})
    else:
        common.report(pictures(args.source, args.folder, args.view, args.look))


if __name__ == "__main__":
    main()
