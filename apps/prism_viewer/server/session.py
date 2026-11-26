"""The render side, on the main thread: the card's session and the Loop of the choice;
a frame for the newest pose, its picture handed to the encoders, the requests applied
between frames (choice, size, controls), every failure kept in the state as a notice or
an error, never a crash."""

import contextlib
import time
import traceback

import komorebi as km
import numpy as np
from prism_cli.preset import opened

from prism.loop.report import by_name, columns
from prism_reference.scene.camera import sized_camera
from prism_viewer.server import catalog, encode
from prism_viewer.server.camera import camera_of, diagonal, pose_of
from prism_viewer.server.encoders import Encoders

KEEP_ALIVE_S = 1.0  # a frame a second when nothing is asked and no stream is read
WAIT_S = 0.1  # the longest wait between looks at the requests
CARD_ROWS = 32  # the last rows of a stopped run whose medians the page shows
MS = 1e3
MS_US = 1e-3  # a microsecond's ms


def log(message):
    """A progress line, flushed."""
    print(f"[prism viewer {time.strftime('%H:%M:%S')}] {message}", flush=True)


def card_times(loop, why):
    """The medians in ms of the time columns over the last CARD_ROWS rows of the runs
    stopped so far, a layer unit's by layer (`part`, `part.<i>`), with their count and
    why the run stopped; None without rows."""
    names, _ = columns(loop)
    rows = [by_name(row, names) for row in loop.times()[-CARD_ROWS:] if row is not None]
    if not rows:
        return None
    ms = {
        name: round(
            float(np.median([row[name] for row in rows if name in row])) * MS_US, 4
        )
        for name in dict.fromkeys(name for row in rows for name in row)
    }
    return {"ms": ms, "frames": len(rows), "why": why}


def recovery_text(record):
    """A live recovery's notice: the code's name, the view that stopped, each layer
    grown with its slots before and after, its milliseconds."""
    name = record.get("name", f"code {record['code']}")
    if "view" in record:
        name += f", view {record['view']} {record['kind']}"
    grown = [
        f"{one['layer']} {one['slots'][0]:,} -> {one['slots'][1]:,} slots"
        for one in record.get("grown", [])
    ]
    took = f"{record['ms']:.1f} ms"
    if not grown:
        return f"frame recovered live ({name}) in {took}"
    return f"lists grown live ({name}): {', '.join(grown)} in {took}"


class Render:
    """The render loop over `state` on card `card`."""

    def __init__(self, state, card):
        self.state, self.card = state, card
        self.stack = None  # the card's session, entered
        self.loop = self.scene = self.opened = None
        self.done = (
            None  # the serials of the last frame: (selection, pose, size, control)
        )
        self.failed = 0  # a selection that failed: wait for another
        self.last = 0.0
        self.encoders = Encoders(state)

    def run(self):
        """Frames until the state stops; the loop and the session closed and the
        encoders joined at the end."""
        try:
            while self.step():
                pass
        finally:
            self.close("stop")
            self.encoders.stop()

    def due(self):
        """Under the lock: the stop, or a frame to render (one is asked for, or a stream
        is being read; else one each KEEP_ALIVE_S)."""
        state = self.state
        if state.stopping:
            return True
        if state.selection == self.failed:
            return False
        serials = (
            state.selection,
            state.pose_serial,
            state.size_serial,
            state.control_serial,
        )
        if serials != self.done or state.watchers:
            return True
        return time.monotonic() - self.last >= KEEP_ALIVE_S

    def step(self):
        """One look at the requests and a frame when one is due; False at the stop."""
        state = self.state
        with state.lock:
            state.changed.wait_for(self.due, timeout=WAIT_S)
            if state.stopping:
                return False
            if not self.due():
                return True
            selection, choice = state.selection, state.choice
        try:
            if self.loop is None or choice != self.opened:
                self.open(choice)
            self.apply()
            self.frame(selection)
        except Exception as error:  # noqa: BLE001 - kept as the state's error
            traceback.print_exc()
            with state.lock:
                state.status = "error"
                state.error = f"{type(error).__name__}: {error}"
                state.notice("error", state.error)
            self.failed = selection
            self.close("error")
        return True

    def open(self, choice):
        """The loop of `choice` (pipeline, scene, view) on a new session at the size
        asked; the pose becomes the view's own."""
        self.close("select")
        state = self.state
        with state.lock:
            state.status, state.loaded, state.controls = "loading", None, []
            state.readings = []
            size = state.size_asked
        name, scene_name, view = choice
        log(f"open {name} on {scene_name} {view or ''} at {size[0]} x {size[1]}")
        began = time.perf_counter()
        preset = opened(name, scene_name, view, size)
        scene = preset.scene
        self.stack = contextlib.ExitStack()
        session = self.stack.enter_context(km.Session(card=self.card))
        self.loop = preset.open(session)
        self.scene, self.opened = scene, choice
        seconds = time.perf_counter() - began
        with state.lock:
            state.loaded = catalog.described(name, preset.globals) | {
                "scene": scene_name,
                "view": view,
                "far_field": preset.far_field,
            }
            state.size, state.capacity = tuple(self.loop.size), self.capacity()
            state.controls = self.loop.controls()
            state.first_pose = pose_of(scene["camera"])
            state.pose = state.first_pose
            state.scene_serial += 1
            state.diagonal = diagonal(scene)
            text = f"loaded {name} on {scene_name}"
            if preset.lacking:
                text += f" without the far field ({preset.missing})"
            state.notice("reload", text, seconds)
        log(f"opened in {seconds:.1f} s")

    def capacity(self):
        """The capacity held, as the page shows it."""
        held = self.loop.held
        return None if held is None else {"tiles": held.tiles, "wide": held.wide}

    def apply(self):
        """The size asked and the controls asked, between frames."""
        state, loop = self.state, self.loop
        with state.lock:
            size = state.size_asked
            asked, state.asked_controls = state.asked_controls, []
        if asked or tuple(size) != tuple(loop.size):
            self.encoders.cut()
        if tuple(size) != tuple(loop.size):
            self.resize(size)
        for serial, name, value in asked:
            reloads = len(loop.reloads)
            try:
                answer = loop.set(name, value)
            except (TypeError, ValueError) as error:
                with state.lock:
                    state.notice("refusal", f"{name}: {error}")
                    state.answer(serial, f"{name}: {error}")
                continue
            with state.lock:
                state.controls = loop.controls()
                state.answer(serial, None)
                if answer == "reload":
                    record = loop.reloads[reloads]
                    state.notice("reload", f"{name} = {value}", record["s"])
                    state.card = card_times(loop, "reload")
                else:
                    state.notice("applied", f"{name} = {value}")

    def resize(self, size):
        """The loop at `size`: a reload past the capacity; refused, the loop opened
        again at the size before."""
        state, loop = self.state, self.loop
        before, began = tuple(loop.size), time.perf_counter()
        try:
            reloaded = loop.resize(size)
        except (ValueError, km.KomorebiError) as error:
            with state.lock:
                state.notice("refusal", f"size {size[0]} x {size[1]}: {error}")
                state.size_asked = before
            log(f"size {size} refused: {error}")
            self.close("refused")
            self.open(self.opened)
            return
        seconds = time.perf_counter() - began
        with state.lock:
            state.size, state.capacity = tuple(loop.size), self.capacity()
            text = f"size {size[0]} x {size[1]}"
            if reloaded:
                state.notice("reload", text, seconds)
                state.card = card_times(loop, "reload")
            else:
                state.notice("applied", text, seconds)

    def frame(self, selection):
        """A frame of the newest pose: the frame, its picture taken into memory of its
        own and handed to the encoders."""
        state, loop = self.state, self.loop
        with state.lock:
            pose, pose_serial = state.pose, state.pose_serial
            own = pose == state.first_pose
            serials = (state.size_serial, state.control_serial)
        camera = self.scene["camera"] if own else camera_of(self.scene["camera"], pose)
        began, recovered = time.perf_counter(), len(loop.recoveries)
        frame = loop.frame(sized_camera(camera, loop.size))
        framed = time.perf_counter()
        self.done = (selection, pose_serial, *serials)
        self.last = time.monotonic()
        if frame.code:
            with state.lock:
                state.code = frame.code
                state.notice("refusal", f"frame code {frame.code}")
            return
        picture = loop.picture()
        if picture is None:
            raise ValueError("no host of the pipeline gives a picture")
        image = encode.held(picture, loop.size)
        taken = time.perf_counter()
        times = {
            "frame": round((framed - began) * MS, 3),
            "picture": round((taken - framed) * MS, 3),
        }
        self.encoders.give(pose_serial, image, times)
        readings = self.readings()
        with state.lock:
            state.readings = readings
        with state.lock:
            for record in loop.recoveries[recovered:]:
                state.notice("grown", recovery_text(record))
            if frame.reloads:
                record = loop.reloads[-1]
                text = f"frame recovered by a reload ({record['why']})"
                state.notice("reload", text, record["s"])
                state.card = card_times(loop, "reload")

    def readings(self):
        """What the hosts that give readings say now, by implementation."""
        out = []
        for implementation, host in self.loop.loaded.hosts.items():
            given = getattr(host, "readings", None)
            if callable(given):
                out.append({"name": implementation} | given())
        return out

    def close(self, why):
        """The pictures in flight not shown, the loop stopped (the card's medians of
        its run kept) and the session closed."""
        self.encoders.cut()
        loop, self.loop = self.loop, None
        if loop is not None:
            try:
                loop.stop()
                with self.state.lock:
                    self.state.card = card_times(loop, why)
            except Exception:  # noqa: BLE001 - the stop of a failed run
                traceback.print_exc()
        if self.stack is not None:
            stack, self.stack = self.stack, None
            try:
                stack.close()
            except Exception:  # noqa: BLE001 - the close of a failed session
                traceback.print_exc()
