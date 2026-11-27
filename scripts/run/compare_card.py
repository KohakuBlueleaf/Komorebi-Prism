"""The card's picture of an opened scene for `compare.py`: a preset's frames on the scene's
view `camera`, the last picture written as a PNG; with --off, a control turned off and
the frames again, that picture beside it; with --plain, the pictures for the passes drawn
under the plain tone (curve 0, saturation 1) and the power transfer at GAMMA (no view
transform) after the whole picture; one JSON line
(codes, far field, tone). `compare_card.py NAME --pipeline P --size W H --frames N
--card C --out FILE.png [--off CONTROL] [--plain]`"""

import argparse
import json
import time
from pathlib import Path

import komorebi as km
from prism_cli.preset import opened

from prism_reference.io.png import write_png
from prism_reference.post.display import GAMMA
from prism_reference.post.tone import CURVE_PLAIN
from prism_reference.scene.artist.entry import VIEW
from prism_reference.scene.camera import sized_camera

LIGHT = "direct.light"  # the light unit's hosts: their tone
PLAIN = {"saturation": 1.0, "curve": CURVE_PLAIN}  # the tone the passes are drawn under
DISPLAY = {"transfer": "power", "gamma": GAMMA}  # and the display's transfer


def frames(loop, camera, count, codes):
    """`count` frames on the camera, the last with its picture; the picture or None."""
    picture = None
    for index in range(count):
        frame = loop.frame(camera, index == count - 1)
        codes.append(frame.code)
        picture = frame.picture if frame.picture is not None else picture
        if frame.code:
            return None
    return picture


def control_named(loop, name):
    """The loop's control `name`, or the one whose name ends in `.name`."""
    names = [c.name for c in loop.controls()]
    found = [n for n in names if n == name or n.endswith(f".{name}")]
    if len(found) != 1:
        raise ValueError(f"control {name!r}: {found or 'none'} among {names}")
    return found[0]


def tone_of(loop):
    """The tone of the loop's light unit (exposure, saturation, curve), or None."""
    for name, host in loop.loaded.hosts.items():
        if name.startswith(LIGHT) and hasattr(host, "tone"):
            return dict(host.tone)
    return None


def main():
    """Draws the frames and writes the last picture."""
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("name")
    parser.add_argument("--pipeline", required=True)
    parser.add_argument("--size", type=int, nargs=2, required=True)
    parser.add_argument("--frames", type=int, default=16)
    parser.add_argument("--card", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--off", default=None, help="a control (or its last part) turned off"
    )
    parser.add_argument(
        "--plain", action="store_true", help="the pass pictures under the plain tone"
    )
    args = parser.parse_args()
    started = time.perf_counter()
    preset = opened(args.pipeline, args.name, VIEW, tuple(args.size))
    codes, pictures, refused, tone, off = [], {}, None, None, None
    with km.Session(card=args.card) as session:
        try:
            loop = preset.open(session)
        except (ValueError, km.KomorebiError) as error:
            refused = f"{type(error).__name__}: {error}"
        if refused is None:
            try:
                camera = sized_camera(preset.scene["camera"], loop.size)
                pictures[args.out] = frames(loop, camera, args.frames, codes)
                tone = tone_of(loop)
                if args.plain and pictures[args.out] is not None:
                    for name, value in (PLAIN | DISPLAY).items():
                        loop.set(control_named(loop, name), value)
                    tone = tone_of(loop)
                    plain = args.out.with_name(f"{args.out.stem}_plain.png")
                    pictures[plain] = frames(loop, camera, args.frames, codes)
                if args.off is not None and pictures[args.out] is not None:
                    try:
                        loop.set(control_named(loop, args.off), False)
                        off = args.out.with_name(f"{args.out.stem}_off.png")
                        pictures[off] = frames(loop, camera, args.frames, codes)
                    except ValueError as error:
                        off = f"{type(error).__name__}: {error}"
            finally:
                loop.stop()
    for path, picture in pictures.items():
        if picture is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            write_png(path, picture[..., :3])
    picture = pictures.get(args.out)
    record = {"name": args.name, "pipeline": args.pipeline, "size": list(preset.size)}
    record |= {"frames": len(codes), "codes": codes, "refused": refused}
    record |= {"far_field": preset.far_field, "picture": args.out.name}
    record |= {"tone": tone, "off": off if not isinstance(off, Path) else off.name}
    record |= {"plain": args.plain}
    record |= {"seconds": round(time.perf_counter() - started, 1)}
    print(json.dumps(record), flush=True)
    raise SystemExit(2 if refused else 1 if any(codes) or picture is None else 0)


if __name__ == "__main__":
    main()
