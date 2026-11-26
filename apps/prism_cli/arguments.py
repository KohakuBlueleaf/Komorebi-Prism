"""The command line's arguments: `run`, `open` and their options."""

import argparse
import ast
from pathlib import Path

from prism.loop.path import PATHS


def option(text):
    """KEY=VALUE as (key, a Python literal, else the text)."""
    key, _, value = text.partition("=")
    if not key or not _:
        raise argparse.ArgumentTypeError(f"{text!r} is not KEY=VALUE")
    try:
        return key, ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return key, value


def parser():
    """The command line's parser."""
    top = argparse.ArgumentParser(prog="prism_cli", description="Komorebi-Prism")
    commands = top.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="a pipeline's frames along a camera path")
    run.add_argument("--pipeline", required=True, help="a preset of configs/pipeline")
    run.add_argument("--scene", required=True)
    run.add_argument("--view", default=None, help="a public scene's view")
    run.add_argument("--size", type=int, nargs=2, default=None, metavar=("W", "H"))
    run.add_argument("--frames", type=int, default=None, help="the preset's if none")
    run.add_argument("--path", choices=tuple(PATHS), default="still")
    run.add_argument(
        "--resize",
        type=int,
        nargs=3,
        action="append",
        default=[],
        metavar=("W", "H", "AT"),
        help="the size from frame AT (from 0) on",
    )
    run.add_argument(
        "--check",
        type=int,
        nargs="+",
        default=[],
        metavar="FRAME",
        help="frames (from 0) whose picture is compared with the preset's REFERENCE",
    )
    run.add_argument(
        "--pictures",
        action="store_true",
        help="every frame's picture taken (the host's frame: the frame and its picture)",
    )
    run.add_argument("--cores", type=int, default=None, help="every core if none")
    run.add_argument("--option", type=option, action="append", default=[])
    run.add_argument("--card", type=int, default=0)
    run.add_argument("--name", default=None, help="the record's file stem")
    run.add_argument("--out", type=Path, default=None, help="the record's folder")
    opening(commands)
    return top


def opening(commands):
    """The command `open`: a scene file converted once, its lights, a preset's frames."""
    one = commands.add_parser("open", help="a scene file converted once and drawn")
    one.add_argument("file", type=Path, help="a glTF file (.glb or .gltf)")
    one.add_argument(
        "--pipeline", default="textured", help="a preset of configs/pipeline"
    )
    one.add_argument("--size", type=int, nargs=2, default=None, metavar=("W", "H"))
    one.add_argument("--camera", default=None, help="the view's camera node")
    one.add_argument("--frames", type=int, default=16)
    one.add_argument("--card", type=int, default=0)
    one.add_argument("--out", type=Path, default=Path("."), help="the picture's folder")
    one.add_argument(
        "--bake",
        choices=("wait", "background", "none"),
        default="background",
        help="the sky's visibility: baked first, in a process of its own, or not",
    )
    one.add_argument(
        "--most-triangles", type=int, default=None, help="none refused if none"
    )
