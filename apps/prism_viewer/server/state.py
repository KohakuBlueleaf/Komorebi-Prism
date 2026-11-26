"""What the HTTP threads and the render loop share: the requests waiting to be applied,
and what the page reads (the choice, the size, the controls, the last frame's numbers,
notices). `lock` guards it all; `changed` wakes the render loop, `framed` the streams,
`answered` the requests waiting for a control's answer.
"""

import collections
import threading
import time

from prism_viewer.server.camera import FOV_LEAST, FOV_MOST

FPS_WINDOW_S = 1.0  # a rate: the events of the last this many seconds
NOTICES = 8  # the notices kept, newest last


class State:
    """The shared state; requests are recorded with a serial, the render loop takes
    the newest of each between frames."""

    def __init__(self, choice, size):
        self.lock = threading.Lock()
        self.changed = threading.Condition(self.lock)
        self.framed = threading.Condition(self.lock)
        self.answered = threading.Condition(self.lock)
        self.stopping = False
        # requests: the choice, the pose, the size, the controls in order
        self.choice, self.selection = tuple(choice), 1
        self.pose, self.pose_serial = None, 0
        self.size_asked, self.size_serial = tuple(size), 0
        self.asked_controls, self.control_serial = [], 0
        self.answers = {}  # a control request's serial: its refusal, or None
        # what the render loop made
        self.status, self.error = "loading", None
        self.loaded = None  # {pipeline, scene, view, about, writes, implementations}
        self.size = None
        self.capacity = None
        self.controls = []  # prism.core.control.Control, named <implementation>.<name>
        self.readings = []  # the hosts' readings, as they name them
        self.scene_serial, self.first_pose, self.diagonal = 0, None, 1.0
        self.times, self.card = {}, None
        self.jpeg, self.frame_number, self.frame_pose = None, 0, 0
        self.frame_at, self.served = None, collections.deque()
        self.watchers = 0  # the streams being read: frames are made while there is one
        self.made, self.replacements = collections.deque(), collections.deque()
        self.replaced, self.encoders = 0, 0
        self.code = 0
        self.notices, self.notice_serial = collections.deque(maxlen=NOTICES), 0

    # Requests (HTTP threads)

    def ask_pose(self, pose, scene_serial):
        """A pose for the scene it was made in (without a field of view: the one
        before); False when the scene has changed."""
        with self.lock:
            if scene_serial != self.scene_serial:
                return False
            if pose.get("fov") is None and self.pose is not None:
                pose = pose | {"fov": self.pose.get("fov")}
            self.pose, self.pose_serial = pose, self.pose_serial + 1
            self.changed.notify_all()
            return self.pose_serial

    def ask_size(self, size):
        """A frame size, applied between frames (a load takes the last asked)."""
        with self.lock:
            self.size_asked, self.size_serial = tuple(size), self.size_serial + 1
            self.changed.notify_all()

    def select(self, choice):
        """A pipeline, scene and view to load."""
        with self.lock:
            self.choice, self.selection = tuple(choice), self.selection + 1
            self.changed.notify_all()

    def ask_control(self, name, value):
        """A control's value (checked against its Control), applied between frames:
        its request's serial."""
        with self.lock:
            control = {one.name: one for one in self.controls}.get(name)
            if control is None:
                raise ValueError(f"no control {name!r}")
            self.control_serial += 1
            self.asked_controls.append(
                (self.control_serial, name, control.checked(value))
            )
            self.changed.notify_all()
            return self.control_serial

    def answer_of(self, serial, timeout):
        """The render loop's answer to control request `serial`: (True, None) applied,
        (True, reason) refused, (False, None) not yet after `timeout`."""
        with self.lock:
            self.answered.wait_for(
                lambda: self.stopping or serial in self.answers, timeout
            )
            if serial not in self.answers:
                return False, None
            return True, self.answers.pop(serial)

    def answer(self, serial, refusal):
        """Under the lock: control request `serial` applied (refusal None) or refused
        with its reason; the waiting request woken."""
        self.answers[serial] = refusal
        self.answered.notify_all()

    def watched(self, by):
        """A stream opened (`by` 1) or closed (-1); the render loop woken by the first."""
        with self.lock:
            self.watchers += by
            self.changed.notify_all()

    def stop(self):
        """The render loop and the streams end."""
        with self.lock:
            self.stopping = True
            self.changed.notify_all()
            self.framed.notify_all()
            self.answered.notify_all()

    # The render loop

    def notice(self, kind, text, seconds=None):
        """A notice under the lock: kind (reload, grown, refusal, applied, error), its text,
        its seconds when it took some."""
        self.notice_serial += 1
        self.notices.append(
            {
                "serial": self.notice_serial,
                "kind": kind,
                "text": text,
                "seconds": None if seconds is None else round(seconds, 3),
                "at": time.time(),
            }
        )

    def framed_now(self, jpeg, pose_serial, times, code):
        """A new frame's JPEG and numbers; the streams woken."""
        with self.lock:
            now = time.monotonic()
            self.jpeg, self.frame_pose, self.times, self.code = (
                jpeg,
                pose_serial,
                times,
                code,
            )
            self.frame_number += 1
            self.frame_at = now
            self.served.append(now)
            self.status, self.error = "running", None
            self.framed.notify_all()

    def made_now(self, replaced, encoders):
        """A picture handed to the `encoders` encoders; `replaced`: it replaced one
        still waiting to be encoded."""
        with self.lock:
            now = time.monotonic()
            self.made.append(now)
            if replaced:
                self.replacements.append(now)
                self.replaced += 1
            self.encoders = encoders
            self.window(now)

    def window(self, now):
        """Under the lock: the rates' events older than FPS_WINDOW_S dropped."""
        for times in (self.served, self.made, self.replacements):
            while times and now - times[0] > FPS_WINDOW_S:
                times.popleft()

    def next_jpeg(self, after, timeout):
        """(number, pose serial, JPEG) of the newest frame once past `after`; (after,
        0, None) after `timeout` or at the stop."""
        with self.lock:
            self.framed.wait_for(
                lambda: self.stopping or self.frame_number > after, timeout
            )
            if self.frame_number > after and self.jpeg is not None:
                return self.frame_number, self.frame_pose, self.jpeg
            return after, 0, None

    # What the page reads

    def snapshot(self):
        """The page's state as plain values."""
        with self.lock:
            now = time.monotonic()
            self.window(now)
            age = None if self.frame_at is None else now - self.frame_at
            return {
                "status": self.status,
                "error": self.error,
                "choice": list(self.choice),
                "loaded": self.loaded,
                "size": None if self.size is None else list(self.size),
                "size_asked": list(self.size_asked),
                "capacity": self.capacity,
                "controls": [control.described() for control in self.controls],
                "readings": self.readings,
                "scene_serial": self.scene_serial,
                "first_pose": self.first_pose,
                "fov": None if self.pose is None else self.pose.get("fov"),
                "fov_limits": [FOV_LEAST, FOV_MOST],
                "diagonal": self.diagonal,
                "frame": self.frame_number,
                "frame_pose": self.frame_pose,
                "code": self.code,
                "fps": len(self.served) / FPS_WINDOW_S,
                "made_fps": len(self.made) / FPS_WINDOW_S,
                "replaced_fps": len(self.replacements) / FPS_WINDOW_S,
                "replaced": self.replaced,
                "encoders": self.encoders,
                "picture_age_s": None if age is None else round(age, 3),
                "times": self.times,
                "card": self.card,
                "notices": list(self.notices),
            }
