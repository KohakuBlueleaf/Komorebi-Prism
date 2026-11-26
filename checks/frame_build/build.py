"""The script a prebuild runs: the handler `work` composed from the arguments, made on
the session and loaded (its kernels built for all five CPUs)."""

import argparse

import komorebi as km

from prism.program.dispatch import thread as dispatch
from prism.program.frame import host as frame_host

RASTER_DEFINES = "prism.stages.raster.capacity:capacity_defines"


def options_of(args):
    """The frame host's options from the command line."""
    return {
        frame_host.THREAD: args.thread,
        frame_host.KINDS: tuple(args.kinds),
        frame_host.LAYERS: tuple(args.layers),
        frame_host.DISPATCH: dispatch.capacity_of(args.ranges, args.across, args.down),
        frame_host.DEFINES: tuple(args.defines),
    }


def parser():
    """The arguments of the build and of its launcher."""
    out = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    out.add_argument("thread", help="the tile thread, a dotted path module:name")
    out.add_argument("--kinds", nargs="*", default=(), help="kinds, dotted paths")
    out.add_argument("--layers", nargs="*", default=("opaque",), help="layer names")
    out.add_argument(
        "--defines",
        nargs="*",
        default=(RASTER_DEFINES,),
        help="functions of the capacity giving build defines (grid.h needs raster's)",
    )
    out.add_argument("--ranges", type=int, default=256, help="count ranges a view")
    out.add_argument("--across", type=int, default=60, help="tiles a row at most")
    out.add_argument("--down", type=int, default=34, help="tile rows at most")
    return out


def main():
    args = parser().parse_args()
    with km.Session() as session:
        host = frame_host.FrameHost(session, None, options_of(args))
        host.prepare()
        program = frame_host.made(host)
        run = session.load(program)
        run.stop()
        print(f"frame build: work loaded, {program.sizes.text}", flush=True)


if __name__ == "__main__":
    main()
