"""python -m prism_viewer.server --host 127.0.0.1 --port P --token T [--pipeline NAME]
[--scene NAME [--view NAME]] [--size W H] [--card N] [--offer NAME ...]: the viewer's
server (offering only the presets named, and the scenes they run on); the render
loop on the main thread, the HTTP side on another; SIGINT or SIGTERM stops both."""

import argparse
import signal
import sys
import threading

from prism_reference.scene.frame import frame_size
from prism_viewer.server import catalog
from prism_viewer.server.app import server
from prism_viewer.server.session import Render, log
from prism_viewer.server.state import State


def parse():
    parser = argparse.ArgumentParser(prog="prism_viewer.server")
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--pipeline", default="raster")
    parser.add_argument("--scene", default="tiny")
    parser.add_argument("--view", default=None, help="a public scene's view")
    parser.add_argument("--size", type=int, nargs=2, default=None, metavar=("W", "H"))
    parser.add_argument("--card", type=int, default=0)
    parser.add_argument(
        "--offer", nargs="+", default=None, metavar="NAME", help="the presets offered"
    )
    return parser, parser.parse_args()


def main():
    parser, args = parse()
    try:
        known = catalog.catalog(args.offer)
        choice = catalog.checked((args.pipeline, args.scene, args.view), known)
    except ValueError as error:
        parser.error(str(error))
    size = tuple(args.size or frame_size({}))
    state = State(choice, size)
    http = server(args.host, args.port, state, args.token, known)
    for number in (signal.SIGINT, signal.SIGTERM):  # only the flag: no lock taken
        signal.signal(number, lambda *_: setattr(state, "stopping", True))
    threading.Thread(target=http.serve_forever, name="http", daemon=True).start()
    log(f"serving on http://{args.host}:{args.port}/?token=...")
    Render(state, args.card).run()  # the main thread owns the card's session
    log("stopping: the loop stopped and the session closed")
    state.stop()
    http.shutdown()
    http.server_close()
    log("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
