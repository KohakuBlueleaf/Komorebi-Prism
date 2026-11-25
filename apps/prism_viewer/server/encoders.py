"""The encode stage: threads that make the JPEGs of the pictures the render loop hands
over. One picture waits at most (a newer one replaces it); the JPEGs reach the state in
the order the pictures were handed over, a late one dropped; a cut drops every picture
handed over before it."""

import collections
import contextlib
import math
import os
import statistics
import tempfile
import threading
import time
import traceback

from prism_viewer.server import encode

LEAST_ENCODERS = 1
MEMORY = "/dev/shm"  # a tmpfs: an encoder's file is a picture a frame, kept off disks
WINDOW = 16  # the hand-overs and encodes whose medians size the stage
MS = 1e3


class Encoders:
    """Encoder threads over `state`: as many as the median encode over the median time
    between hand-overs asks, from LEAST_ENCODERS to the CPUs allowed but one."""

    def __init__(self, state):
        self.state = state
        self.cond = threading.Condition()
        self.threads = []
        self.most = max(LEAST_ENCODERS, len(os.sched_getaffinity(0)) - 1)
        self.waiting = None  # (number, pose serial, image, times) of the next picture
        self.handed = 0  # the number of the last picture handed over
        self.shown = 0  # the number of the last picture given to the state
        self.cutoff = 0  # pictures numbered up to this are not shown
        self.stopping = False
        self.encodes = collections.deque(maxlen=WINDOW)  # ms
        self.gaps = collections.deque(maxlen=WINDOW)  # ms between hand-overs
        self.last = None
        self.grow()

    def give(self, pose_serial, image, times):
        """A picture handed over, never waited for: True when it replaced one that was
        still waiting."""
        now = time.perf_counter()
        with self.cond:
            if self.last is not None:
                self.gaps.append((now - self.last) * MS)
            self.last = now
            self.handed += 1
            replaced = self.waiting is not None
            self.waiting = (self.handed, pose_serial, image, times)
            self.cond.notify()
            self.grow()
            count = len(self.threads)
        self.state.made_now(replaced, count)
        return replaced

    def cut(self):
        """The pictures handed over so far are not shown."""
        with self.cond:
            self.waiting = None
            self.cutoff = self.handed

    def stop(self):
        """The threads ended and joined; the pictures in flight not shown."""
        with self.cond:
            self.stopping, self.waiting = True, None
            self.cutoff = self.handed
            self.cond.notify_all()
            threads = list(self.threads)
        for thread in threads:
            thread.join()

    def grow(self):
        """Under the lock: threads started up to the count the medians ask."""
        wanted = LEAST_ENCODERS
        if self.encodes and self.gaps:
            gap = max(statistics.median(self.gaps), 1e-3)
            wanted = math.ceil(statistics.median(self.encodes) / gap)
        while len(self.threads) < min(max(LEAST_ENCODERS, wanted), self.most):
            thread = threading.Thread(
                target=self.work, name=f"encode {len(self.threads)}", daemon=True
            )
            self.threads.append(thread)
            thread.start()

    def work(self):
        """One encoder: the waiting picture taken, encoded into a file of its own in
        MEMORY (without MEMORY, into memory of the process), given to the state when no
        newer one was."""
        with (
            tempfile.TemporaryFile(dir=MEMORY)
            if os.path.isdir(MEMORY)
            else contextlib.nullcontext()
        ) as out:
            while True:
                with self.cond:
                    self.cond.wait_for(lambda: self.stopping or self.waiting)
                    if self.stopping:
                        return
                    (number, pose_serial, image, times), self.waiting = (
                        self.waiting,
                        None,
                    )
                began = time.perf_counter()
                try:
                    data = encode.jpeg(image, out)
                except Exception as error:  # noqa: BLE001 - kept as a notice
                    traceback.print_exc()
                    with self.state.lock:
                        self.state.notice("error", f"encode: {error}")
                    continue
                ms = (time.perf_counter() - began) * MS
                with self.cond:
                    self.encodes.append(ms)
                    if number <= max(self.shown, self.cutoff):
                        continue
                    self.shown = number
                    times = times | {"encode": round(ms, 3)}
                    self.state.framed_now(data, pose_serial, times, 0)
