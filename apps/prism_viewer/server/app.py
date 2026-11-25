"""The HTTP side: the routes under /api (each refused with 403 without the token: the
query `token` on a GET, the header X-Token on a POST), the frames as a multipart JPEG
stream, and the built page's files."""

import hmac
import json
import mimetypes
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from prism_reference.scene.frame import frame_grid
from prism_viewer.server import camera, catalog

TOKEN_HEADER = "X-Token"
BOUNDARY = "frame"
MOST_BODY_BYTES = 1 << 16
STREAM_WAIT_S = 1.0
ANSWER_WAIT_S = 60.0  # a control request waits this long for the render loop's answer
DIST = Path(__file__).resolve().parents[1] / "web" / "dist"


def size_of(body):
    """A frame size from a request's JSON: whole positive width and height."""
    width, height = body["width"], body["height"]
    if not all(isinstance(n, int) and not isinstance(n, bool) for n in (width, height)):
        raise ValueError("a size is a whole width and height in pixels")
    frame_grid((width, height))
    return width, height


def handler_class(state, token, known, dist=DIST):
    """The request handler, bound to the state, the token, the catalog `known` and the
    built page's folder."""

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format, *args):
            pass

        def allowed(self, given):
            if given is not None and hmac.compare_digest(given, token):
                return True
            self.reply(403, b"forbidden\n", "text/plain")
            return False

        def reply(self, code, body, kind):
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def reply_json(self, code, value):
            self.reply(code, json.dumps(value).encode(), "application/json")

        def do_GET(self):
            url = urllib.parse.urlsplit(self.path)
            if not url.path.startswith("/api/"):
                self.static(url.path)
                return
            query = urllib.parse.parse_qs(url.query)
            if not self.allowed(query.get("token", [None])[0]):
                return
            match url.path:
                case "/api/state":
                    self.reply_json(200, state.snapshot())
                case "/api/catalog":
                    self.reply_json(200, known)
                case "/api/stream":
                    self.stream()
                case _:
                    self.reply(404, b"not found\n", "text/plain")

        def do_POST(self):
            url = urllib.parse.urlsplit(self.path)
            if not url.path.startswith("/api/") or not self.allowed(
                self.headers.get(TOKEN_HEADER)
            ):
                if not url.path.startswith("/api/"):
                    self.reply(404, b"not found\n", "text/plain")
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                if not 0 <= length <= MOST_BODY_BYTES:
                    raise ValueError("a body of that size is not taken")
                body = json.loads(self.rfile.read(length) or b"{}")
                match url.path:
                    case "/api/pose":
                        serial = int(body.get("scene_serial", -1))
                        taken = state.ask_pose(camera.parsed(body), serial)
                        self.reply_json(200, {"taken": taken})
                    case "/api/size":
                        state.ask_size(size_of(body))
                        self.reply_json(200, {"taken": True})
                    case "/api/select":
                        choice = (body["pipeline"], body["scene"], body.get("view"))
                        state.select(catalog.checked(choice, known))
                        self.reply_json(200, {"taken": True})
                    case "/api/control":
                        serial = state.ask_control(str(body["name"]), body["value"])
                        done, refusal = state.answer_of(serial, ANSWER_WAIT_S)
                        if refusal is not None:
                            self.reply_json(400, {"error": refusal, "noticed": True})
                        else:
                            self.reply_json(200, {"taken": True, "applied": done})
                    case _:
                        self.reply(404, b"not found\n", "text/plain")
            except (ValueError, KeyError, TypeError) as error:
                self.reply_json(400, {"error": str(error)})

        def static(self, path):
            root = dist.resolve()
            relative = path.lstrip("/") or "index.html"
            file = (root / urllib.parse.unquote(relative)).resolve()
            if not file.is_relative_to(root) or not file.is_file():
                file = root / "index.html"
            if not file.is_file():
                self.reply(
                    404, b"the page is not built (npm run build)\n", "text/plain"
                )
                return
            kind = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
            self.reply(200, file.read_bytes(), kind)

        def stream(self):
            self.close_connection = True
            self.send_response(200)
            self.send_header(
                "Content-Type", f"multipart/x-mixed-replace; boundary={BOUNDARY}"
            )
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            number = 0
            state.watched(1)
            try:
                while not state.stopping:
                    number, pose, data = state.next_jpeg(number, STREAM_WAIT_S)
                    if data is None:
                        continue
                    head = (
                        f"--{BOUNDARY}\r\nContent-Type: image/jpeg\r\n"
                        f"Content-Length: {len(data)}\r\n"
                        f"X-Frame: {number}\r\nX-Pose: {pose}\r\n\r\n"
                    )
                    self.wfile.write(head.encode() + data + b"\r\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                state.watched(-1)

    return Handler


def server(host, port, state, token, known):
    """The threading HTTP server on (host, port)."""
    made = ThreadingHTTPServer((host, port), handler_class(state, token, known))
    made.daemon_threads = True
    return made
