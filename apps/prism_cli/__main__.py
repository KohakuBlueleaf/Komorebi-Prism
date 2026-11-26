"""python -m prism_cli <command> ..."""

import sys

from prism_cli.arguments import parser
from prism_cli.open_file import open_command
from prism_cli.run import run

COMMANDS = {"run": run, "open": open_command}


def main():
    args = parser().parse_args()
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
