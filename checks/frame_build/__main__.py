"""The handler `work` of a tile thread and kinds (dotted paths) built with no card: the
build script run by Komorebi's prebuild. Example:
python -m checks.frame_build checks.frame_build.toy:TOY"""

import sys
from pathlib import Path

from komorebi.builder import prebuild

from checks.frame_build.build import parser

SCRIPT = Path(__file__).resolve().parent / "build.py"


def main():
    parser().parse_args()  # refused here, before a process starts
    return prebuild.run(SCRIPT, sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
