"""Writes the generated scenes as <out>/<name>.npz and prints their sizes and checksums."""

import argparse
from pathlib import Path

from prism_reference.scene.files import checksum, save_scene
from prism_reference.scene.generated import PRESETS, make_preset


def main():
    """Writes the preset scenes as <out>/<name>.npz and prints their sizes."""
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("names", nargs="*", default=list(PRESETS))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for name in args.names:
        scene = make_preset(name)
        save_scene(args.out / f"{name}.npz", scene)
        t, v = scene["meta"][:2]
        print(f"{name}: {t} triangles, {v} vertices, sha256 {checksum(scene)}")


if __name__ == "__main__":
    main()
