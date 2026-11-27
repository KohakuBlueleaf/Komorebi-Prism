"""The card's picture of an opened scene for `compare.py`: a preset's frames on the scene's
view `camera`, the last picture written as a PNG, one JSON line (the codes, the far
field, the seconds). `compare_card.py NAME --pipeline P --size W H --frames N --card C
--out FILE.png`"""

import argparse
import json
import time
from pathlib import Path

import komorebi as km
from prism_cli.preset import opened

from prism_reference.io.png import write_png
from prism_reference.scene.artist.entry import VIEW
from prism_reference.scene.camera import sized_camera


def main():
    """Draws the frames and writes the last picture."""
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("name")
    parser.add_argument("--pipeline", required=True)
    parser.add_argument("--size", type=int, nargs=2, required=True)
    parser.add_argument("--frames", type=int, default=16)
    parser.add_argument("--card", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    preset = opened(args.pipeline, args.name, VIEW, tuple(args.size))
    codes, picture, refused = [], None, None
    with km.Session(card=args.card) as session:
        try:
            loop = preset.open(session)
        except (ValueError, km.KomorebiError) as error:
            refused = f"{type(error).__name__}: {error}"
        if refused is None:
            try:
                camera = sized_camera(preset.scene["camera"], loop.size)
                for index in range(args.frames):
                    frame = loop.frame(camera, index == args.frames - 1)
                    codes.append(frame.code)
                    picture = frame.picture if frame.picture is not None else picture
                    if frame.code:
                        break
            finally:
                loop.stop()
    if picture is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        write_png(args.out, picture[..., :3])
    record = {"name": args.name, "pipeline": args.pipeline, "size": list(preset.size)}
    record |= {"frames": len(codes), "codes": codes, "refused": refused}
    record |= {"far_field": preset.far_field, "picture": args.out.name}
    record |= {"seconds": round(time.perf_counter() - started, 1)}
    print(json.dumps(record), flush=True)
    raise SystemExit(2 if refused else 1 if any(codes) or picture is None else 0)


if __name__ == "__main__":
    main()
