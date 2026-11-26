"""The job thread on a loaded run: its shared regions written and read by name, its job
commands submitted to the lead and waited for, their numbers for a graph."""

import komorebi as km
import numpy as np

from prism.program.jobs.thread import CLUSTERS, lead

TIMEOUT = 60.0  # seconds a job command waits for its event


def words_of(value):
    """A number or an array as uint32 words (a float array as its float32 bits)."""
    array = np.atleast_1d(np.asarray(value))
    if array.dtype.kind == "f":
        array = array.astype(np.float32).view(np.uint32)
    return array.astype(np.uint32).reshape(-1)


class JobThread:
    """The job thread of `run` laid out by `layout` (a JobLayout) on `clusters`."""

    def __init__(self, run, layout, clusters=CLUSTERS):
        self.run = run
        self.layout = layout
        self.lead = lead(clusters)
        self.thread = run.threads[self.lead]

    def write(self, name, data, at=0):
        """`data`'s words into the region `name` from byte `at`; ValueError past its
        end."""
        _, _, bytes_, _ = self.layout.regions[name]
        words = words_of(data)
        if at + 4 * len(words) > bytes_:
            raise ValueError(
                f"job region {name!r}: {4 * len(words)} bytes at {at} pass its {bytes_}"
            )
        self.thread.write(name, words, at)

    def read(self, name):
        """The region `name`'s bytes, read after the stop."""
        return np.frombuffer(self.thread.read(name), np.uint8).copy()

    def handler(self, name):
        """The number of the job command `name` (for a graph's node)."""
        return self.layout.handler(name)

    def submit(self, name, args=()):
        """The job command `name` with the words `args` to the lead, not waited for:
        its handle."""
        return self.run.submit(
            self.handler(name), cluster=self.lead, args=list(args), result=True
        )

    def serve(self, name, args=()):
        """The job command `name` waited for: its result word."""
        event = self.run.wait(self.submit(name, args), timeout=TIMEOUT)
        if event.kind != "done":
            raise km.KomorebiError(f"job {name}: {event}")
        return int(event.result)
