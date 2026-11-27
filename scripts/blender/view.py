"""Run inside Blender: a view transform (and look) as the operations this Blender's
OpenColorIO evaluates from scene linear to the display, written as `<stem>.view.npz`;
and a linear picture through Blender's own view transform, for the check.
`blender --background --python view.py -- sidecar <stem.prism.json>`
`blender --background --python view.py -- tables <out.npz> <view> <look> [<display>]`
`blender --background --python view.py -- pictures <linear.npy> <out_dir> <view> <look>`
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import common
import numpy
import PyOpenColorIO as ocio

SUFFIX = ".view.npz"
NO_LOOK = ("", "None")
F = numpy.float32


class Unsupported(Exception):
    """An operation the reference does not evaluate."""


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


def forward(op):
    """True when the operation runs forward."""
    return op.getDirection() == ocio.TRANSFORM_DIR_FORWARD


def matrix_op(op):
    """A matrix and offset; the alpha row and column must be the identity's."""
    m = numpy.array(op.getMatrix(), numpy.float64).reshape(4, 4)
    offset = numpy.array(op.getOffset(), numpy.float64)
    alpha = numpy.array([0.0, 0.0, 0.0, 1.0])
    if not (
        numpy.array_equal(m[3], alpha)
        and numpy.array_equal(m[:3, 3], alpha[:3])
        and offset[3] == 0
    ):
        raise Unsupported("a matrix that mixes alpha")
    m, offset = m[:3, :3], offset[:3]
    if not forward(op):
        m = numpy.linalg.inv(m)
        offset = -m @ offset
    return "matrix", {"matrix": m, "offset": offset}


def log_op(op):
    """A logarithm of a base, or its inverse."""
    kind = "log" if forward(op) else "antilog"
    return kind, {"base": numpy.array(op.getBase(), numpy.float64)}


def exponent_op(op):
    """A power per channel; negatives clamped to 0."""
    if op.getNegativeStyle() != ocio.NEGATIVE_CLAMP:
        raise Unsupported(f"an exponent with negative style {op.getNegativeStyle()}")
    value = numpy.array(op.getValue()[:3], numpy.float64)
    return "power", {"power": value if forward(op) else 1.0 / value}


def moncurve_op(op):
    """A power with a linear segment (forward decodes, inverse encodes)."""
    if op.getNegativeStyle() != ocio.NEGATIVE_LINEAR:
        raise Unsupported(f"a moncurve with negative style {op.getNegativeStyle()}")
    numbers = {
        "gamma": numpy.array(op.getGamma()[:3], numpy.float64),
        "offset": numpy.array(op.getOffset()[:3], numpy.float64),
    }
    return ("decode" if forward(op) else "encode"), numbers


def lut1d_op(op):
    """A 1D table over [0, 1], linear between entries."""
    if not forward(op) or op.getInputHalfDomain() or op.getOutputRawHalfs():
        raise Unsupported("a 1D table inverse or over half floats")
    if op.getHueAdjust() != ocio.HUE_NONE:
        raise Unsupported("a 1D table with hue adjustment")
    if op.getInterpolation() not in (ocio.INTERP_LINEAR, ocio.INTERP_DEFAULT):
        raise Unsupported(f"a 1D table with interpolation {op.getInterpolation()}")
    table = numpy.array([op.getValue(i) for i in range(op.getLength())], F)
    return "table", {"table": table}


def lut3d_op(op):
    """A 3D table over [0, 1]^3, indexed [r, g, b], tetrahedral or trilinear."""
    if not forward(op):
        raise Unsupported("an inverse 3D table")
    tetrahedral = op.getInterpolation() in (ocio.INTERP_TETRAHEDRAL, ocio.INTERP_BEST)
    if not tetrahedral and op.getInterpolation() not in (
        ocio.INTERP_LINEAR,
        ocio.INTERP_DEFAULT,
    ):
        raise Unsupported(f"a 3D table with interpolation {op.getInterpolation()}")
    n = op.getGridSize()
    cube = numpy.empty((n, n, n, 3), F)
    for r in range(n):
        for g in range(n):
            for b in range(n):
                cube[r, g, b] = op.getValue(r, g, b)
    kind = "cube_tetrahedral" if tetrahedral else "cube_trilinear"
    return kind, {"cube": cube}


def range_op(op):
    """A range: scale and offset, clamped to the output's bounds when set."""
    if not forward(op) or op.getStyle() != ocio.RANGE_CLAMP:
        raise Unsupported("an inverse or unclamped range")
    if not (op.hasMinInValue() and op.hasMaxInValue()):
        raise Unsupported("a range without both input bounds")
    lo_in, hi_in = op.getMinInValue(), op.getMaxInValue()
    lo_out, hi_out = op.getMinOutValue(), op.getMaxOutValue()
    scale = (hi_out - lo_out) / (hi_in - lo_in)
    numbers = {
        "scale": numpy.array(scale),
        "offset": numpy.array(lo_out - scale * lo_in),
        "low": numpy.array(lo_out if op.hasMinOutValue() else -numpy.inf),
        "high": numpy.array(hi_out if op.hasMaxOutValue() else numpy.inf),
    }
    return "range", numbers


OPERATIONS = {
    "MatrixTransform": matrix_op,
    "LogTransform": log_op,
    "ExponentTransform": exponent_op,
    "ExponentWithLinearTransform": moncurve_op,
    "Lut1DTransform": lut1d_op,
    "Lut3DTransform": lut3d_op,
    "RangeTransform": range_op,
}


def operations(cfg, display, view, look):
    """[(kind, numbers)] of the optimized processor; Unsupported names the first
    operation the reference does not evaluate."""
    found = []
    for op in processor(cfg, display, view, look).createGroupTransform():
        name = type(op).__name__
        if name not in OPERATIONS:
            raise Unsupported(f"the operation {name}")
        found.append(OPERATIONS[name](op))
    return found


def tables(display, view, look):
    """{name: array} of the view's operations, the look dropped (with a note) when an
    operation of it is unsupported; None and the note when the view itself is."""
    cfg = config()
    notes = []
    try:
        found = operations(cfg, display, view, look)
    except Unsupported as error:
        if look in NO_LOOK:
            return None, [f"view transform {view!r}: {error} is not evaluated"]
        notes.append(f"look {look!r}: {error} is not evaluated; the look dropped")
        try:
            found = operations(cfg, display, view, "")
        except Unsupported as again:
            notes.append(f"view transform {view!r}: {again} is not evaluated")
            return None, notes
        look = ""
    record = {
        "kinds": numpy.array([kind for kind, _ in found]),
        "view": numpy.array(view),
        "look": numpy.array(look),
        "display": numpy.array(display),
        "blender": numpy.array(bpy.app.version_string),
        "notes": numpy.array(notes, dtype=str),
    }
    for i, (_, numbers) in enumerate(found):
        record.update({f"op{i}_{name}": value for name, value in numbers.items()})
    return record, notes


def write(path, display, view, look):
    """The view's tables written to `path`; the file's name (None when not written)
    and the notes."""
    record, notes = tables(display, view, look)
    if record is None:
        return None, notes
    with open(path, "wb") as f:
        numpy.savez_compressed(f, **record)
    return os.path.basename(path), notes


def for_sidecar(path):
    """The tables of a sidecar's view written beside it and named in its `render`."""
    with open(path) as f:
        record = json.load(f)
    render = record["render"]
    stem = path[: -len(".prism.json")]
    display = render.get("display") or bpy.context.scene.display_settings.display_device
    name, notes = write(
        stem + SUFFIX, display, render["view_transform"], render["look"]
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
    cpu = processor(config(), display, view, look).getDefaultCPUProcessor()
    flat = numpy.ascontiguousarray(pixels.reshape(-1, 3)).copy()
    cpu.applyRGB(flat)
    numpy.save(os.path.join(folder, "ocio.npy"), flat.reshape(h, w, 3))
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
